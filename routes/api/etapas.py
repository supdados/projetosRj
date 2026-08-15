"""Endpoints JSON de mutação de ETAPAS (Fase 5a) consumidos pela SPA.

Cobre o CRUD de etapas, edição inline de campos (com cascata de datas
server-side), comentários, toggles de iniciada/concluída, reordenação (que
dispara a cascata de datas) e a importação de um modelo de etapas para o
projeto. TODOS no envelope canônico (``ok``/``fail``), protegidos por
``api_login_required`` (401 JSON) e por ``require_project_rank(..., editor)`` —
via o projeto da etapa. Contrato S5 (F4-2/F4-2b): recurso inexistente E recurso
invisível (rank 0) respondem o MESMO 404 (``fail_not_found``); rank >= leitor
insuficiente para a ação responde 403 ``forbidden``.

REUSO sem duplicar regra de negócio:
    - Criação/edição/exclusão/comentário/campo: ``services/etapas_mutation.py``.
    - Cascata de datas em dias úteis: ``services/etapas_cascade.py``
      (``cascade_subsequent_dates``) + ``routes/etapas/helpers.py``
      (``_business_days_between``). O FRONT NUNCA recalcula datas — o endpoint
      devolve o estado atualizado.
    - Importação de modelo: ``services/etapas_import.py``.

ADIADO (NÃO mutado aqui): tarefas das etapas (Fase 5b) e reuniões Google
(Fase 6) — quando uma etapa é reunião Google, as rotas de mutação regular a
recusam (mesma regra das rotas Jinja legadas).

Anexa ao ``main_bp`` ÚNICO; NÃO cria blueprint novo e NÃO altera as rotas
Jinja/legadas (coexistência via strangler).
"""

from __future__ import annotations

import datetime
from typing import Any

from flask import Response, g, request

from models import Etapa, Project, StageTemplate, StageTemplateItem, db
from sqlalchemy import func
from services.etapa_responsaveis import (
    apply_responsaveis_entries,
    areas_from_responsavel_legado,
    parse_responsaveis_entries,
    replace_etapa_responsaveis,
)
from services.etapas_cascade import cascade_subsequent_dates
from services.etapas_import import import_template_stages
from services.etapas_mutation import (
    EtapaNaoEditavelError,
    _validate_date_range,
    assert_etapa_editavel,
    assert_projeto_permite_mutacao_de_etapas,
    count_open_tasks_in_etapa,
    create_etapa_record,
    delete_regular_etapa,
    etapa_tem_responsavel,
    motivo_bloqueio_conclusao,
    save_etapa_comentario,
    update_regular_field,
)
from services.authorization import PAPEL_EDITOR, require_project_rank
from services.project_meetings import is_google_meeting_stage

from ..blueprint import main_bp
from ..shared import log_project_action
from .envelope import fail, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import serialize_etapa_detail, serialize_project_detail

MAX_CASCADE_BUSINESS_DAYS = 365
# "responsavel" fora: o espelho só é escrito pela N:N (POST .../responsaveis).
_REGULAR_FIELDS = {"descricao", "data_inicio", "data_fim"}


def _load_project_or_error(project_id: int) -> tuple[Project | None, Any]:
    """Carrega o projeto: 404 se inexistente OU invisível; 403 se rank < editor."""
    project = db.session.get(Project, project_id)
    denied = require_project_rank(
        project,
        PAPEL_EDITOR,
        message="Você não tem permissão para acessar este projeto.",
    )
    if denied is not None:
        return None, denied
    return project, None


def _load_etapa_or_error(etapa_id: int) -> tuple[Etapa | None, Any]:
    """Carrega a etapa: 404 se inexistente OU invisível; 403 se rank < editor."""
    etapa = db.session.get(Etapa, etapa_id)
    if etapa is None:
        return None, fail_not_found()
    denied = require_project_rank(
        etapa.project,
        PAPEL_EDITOR,
        message="Você não tem permissão para alterar etapas deste projeto.",
    )
    if denied is not None:
        return None, denied
    return etapa, None


def _fail_nao_editavel(exc: EtapaNaoEditavelError) -> Any:
    """Converte a exceção do service no 422 canônico do envelope da API."""
    return fail(exc.motivo, status=422, code="validation")


def _etapa_editavel_ou_422(etapa: Etapa, *, allow_done: bool = False) -> Any | None:
    """Aplica ``assert_etapa_editavel``; devolve o 422 pronto ou ``None``."""
    try:
        assert_etapa_editavel(etapa, allow_done=allow_done)
    except EtapaNaoEditavelError as exc:
        return _fail_nao_editavel(exc)
    return None


def _projeto_editavel_ou_422(project: Project) -> Any | None:
    """Aplica ``assert_projeto_permite_mutacao_de_etapas``; 422 pronto ou ``None``."""
    try:
        assert_projeto_permite_mutacao_de_etapas(project)
    except EtapaNaoEditavelError as exc:
        return _fail_nao_editavel(exc)
    return None


def _etapa_payload(etapa: Etapa) -> dict[str, Any]:
    """Serializa uma etapa para o detalhe, computando a contagem de tarefas.

    Reusa ``serialize_etapa_detail`` (Fase 5a). As tarefas são SOMENTE LEITURA.
    """
    from .project_detail import _task_counts_by_etapa

    counts = _task_counts_by_etapa(etapa.project).get(etapa.id, {})
    return serialize_etapa_detail(
        etapa,
        task_total=counts.get("total", 0),
        task_done=counts.get("done", 0),
    )


def _ordered_etapas_payload(project: Project) -> list[dict[str, Any]]:
    """Lista as etapas do projeto ordenadas, serializadas para o detalhe."""
    from .project_detail import _task_counts_by_etapa

    counts = _task_counts_by_etapa(project)
    etapas = sorted(
        project.etapas, key=lambda e: (e.ordem if e.ordem is not None else 0)
    )
    return [
        serialize_etapa_detail(
            etapa,
            task_total=counts.get(etapa.id, {}).get("total", 0),
            task_done=counts.get(etapa.id, {}).get("done", 0),
        )
        for etapa in etapas
    ]


def _parse_date(value: str | None) -> tuple[datetime.date | None, bool]:
    """Converte ``YYYY-MM-DD`` para ``date``; retorna ``(date, ok)``."""
    if not value:
        return None, True
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date(), True
    except ValueError:
        return None, False


@main_bp.route("/api/projetos/<int:project_id>/etapas", methods=["POST"])
@api_login_required
def api_etapa_add(project_id: int) -> Response | tuple[Response, int]:
    """Adiciona uma etapa ao projeto (envelope), reusando ``create_etapa_record``.

    Espelha a validação da rota Jinja ``add_etapa``: descrição obrigatória, datas
    em ``YYYY-MM-DD`` e a regra "concluída exige iniciada". Quando o projeto está
    Finalizado, exige ``reactivate=true`` no corpo (senão 409 ``validation`` com
    ``confirmation_required``), reativando-o para Vigente como no fluxo legado.

    Returns:
        Envelope com a etapa criada e o status do projeto; 404/403 de acesso;
        422 validação; 409 confirmação de reativação; 401 sem sessão.
    """
    project, error = _load_project_or_error(project_id)
    if error is not None:
        return error

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    descricao = (data.get("descricao") or "").strip()
    if not descricao:
        return fail(
            "A descrição da etapa é obrigatória.", status=422, code="validation"
        )

    try:
        responsaveis_entries = parse_responsaveis_entries(data.get("responsaveis"))
    except ValueError as exc:
        return fail(str(exc), status=422, code="validation")

    # Isenta de assert_etapa_editavel: adicionar etapa REATIVA o projeto Finalizado.
    reactivate = bool(data.get("reactivate"))
    if project.status == "Finalizado" and not reactivate:
        return fail(
            "Ao adicionar uma nova etapa, o projeto voltará para o status Vigente.",
            status=409,
            code="validation",
        )

    data_inicio, ok_i = _parse_date(data.get("data_inicio"))
    data_fim, ok_f = _parse_date(data.get("data_fim"))
    if not ok_i or not ok_f:
        return fail("Formato de data inválido.", status=422, code="validation")

    iniciada = bool(data.get("iniciada"))
    done = bool(data.get("done"))
    if not iniciada and done:
        done = False

    try:
        new_etapa, reactivated = create_etapa_record(
            project,
            descricao=descricao,
            data_inicio=data_inicio,
            data_fim=data_fim,
            responsavel=None,
            comentarios=(data.get("comentarios") or "").strip() or None,
            iniciada=iniciada,
            done=done,
        )
        apply_responsaveis_entries(new_etapa, responsaveis_entries)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return fail(str(exc), status=422, code="validation")
    except Exception:
        db.session.rollback()
        return fail("Erro ao adicionar etapa.", status=422, code="validation")

    return ok(
        {
            "etapa": _etapa_payload(new_etapa),
            "project_status": project.status,
            "project_reactivated": reactivated,
        }
    )


def _tem_responsavel_apos_edicao(etapa: Etapa, data: dict[str, Any]) -> bool:
    """Estado de responsável RESULTANTE: o texto enviado substitui a lista atual."""
    if "responsavel" not in data:
        return etapa_tem_responsavel(etapa)
    return bool(str(data.get("responsavel") or "").strip())


def _aplicar_responsavel_legado(etapa: Etapa, data: dict[str, Any]) -> Any | None:
    """Traduz o texto legado ``responsavel`` para a N:N; devolve o 422 pronto ou ``None``.

    Sem a chave no corpo, responsáveis ficam INTOCADOS — escrever só o espelho
    ``Etapa.responsavel`` dessincronizaria a N:N (auditoria 2026-08-15, item 1.2).
    """
    if "responsavel" not in data:
        return None
    try:
        replace_etapa_responsaveis(
            etapa, areas_from_responsavel_legado(data.get("responsavel"))
        )
    except EtapaNaoEditavelError as exc:
        return _fail_nao_editavel(exc)
    except ValueError as exc:
        return fail(str(exc), status=422, code="validation")
    return None


@main_bp.route("/api/etapas/<int:etapa_id>", methods=["POST"])
@api_login_required
def api_etapa_edit(etapa_id: int) -> Response | tuple[Response, int]:
    """Edita uma etapa regular (envelope) — sucessora da extinta rota Jinja
    ``edit_etapa`` (``/etapa/<id>/edit``, cortada na migração SPA).

    Atualiza descrição/comentários/datas/iniciada/done com as mesmas regras:
    concluir exige iniciada e nenhuma tarefa aberta. Reuniões Google são
    recusadas (Fase 6). Datas em ``YYYY-MM-DD``. O texto legado ``responsavel``,
    quando vem no corpo, é traduzido para a N:N via ``replace_etapa_responsaveis``
    (o espelho nunca é escrito sozinho); sem a chave, responsáveis não mudam.

    Returns:
        Envelope com a etapa atualizada; 404/403 de acesso; 422 validação.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
    blocked = _etapa_editavel_ou_422(etapa, allow_done=True)
    if blocked is not None:
        return blocked
    if is_google_meeting_stage(etapa):
        return fail(
            "Reuniões do Google devem ser editadas pelo fluxo de calendário.",
            status=422,
            code="validation",
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    data_inicio, ok_i = _parse_date(data.get("data_inicio"))
    data_fim, ok_f = _parse_date(data.get("data_fim"))
    if not ok_i or not ok_f:
        return fail("Formato de data inválido.", status=422, code="validation")
    try:
        _validate_date_range(etapa, data_inicio, data_fim)
    except ValueError as exc:
        return fail(str(exc), status=422, code="validation")

    iniciada = bool(data.get("iniciada"))
    done_requested = bool(data.get("done"))

    if not iniciada and done_requested:
        return fail(
            "A etapa não pode ser concluída sem ser iniciada.",
            status=422,
            code="validation",
        )
    if done_requested and not etapa.done:
        # Mesma régua do toggle, sobre os valores CANDIDATOS do request (datas e
        # o texto legado de responsável mudam nesta mesma chamada).
        motivo = motivo_bloqueio_conclusao(
            data_inicio=data_inicio,
            data_fim=data_fim,
            tem_responsavel=_tem_responsavel_apos_edicao(etapa, data),
            tarefas_abertas=count_open_tasks_in_etapa(etapa.id),
        )
        if motivo is not None:
            return fail(motivo, status=422, code="validation")

    # Responsável antes de mutar `done`: o guard do caminho canônico lê o
    # done em memória e recusaria concluir + informar responsável na mesma chamada.
    responsavel_error = _aplicar_responsavel_legado(etapa, data)
    if responsavel_error is not None:
        db.session.rollback()
        return responsavel_error

    old_descricao = etapa.descricao
    etapa.descricao = data.get("descricao")
    etapa.comentarios = data.get("comentarios")
    etapa.iniciada = iniciada
    etapa.done = done_requested
    etapa.data_inicio = data_inicio
    etapa.data_fim = data_fim

    try:
        log_project_action(
            project_id=etapa.project_id,
            action_type="edit_etapa",
            description=f'Editou a etapa "{old_descricao}"',
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao atualizar etapa.", status=422, code="validation")

    return ok({"etapa": _etapa_payload(etapa)})


@main_bp.route("/api/etapas/<int:etapa_id>/delete", methods=["POST"])
@api_login_required
def api_etapa_delete(etapa_id: int) -> Response | tuple[Response, int]:
    """Exclui uma etapa regular (envelope), reusando ``delete_regular_etapa``.

    Reuniões Google são recusadas aqui (a exclusão delas passa pelo fluxo de
    calendário — Fase 6). Desvincula as tarefas (``etapa_id = NULL``) como na
    rota legada.

    Returns:
        Envelope ``{deleted_id, project_id, total_etapas}``; 404/403; 422.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
    if is_google_meeting_stage(etapa):
        return fail(
            "Reuniões do Google são excluídas pelo fluxo de calendário.",
            status=422,
            code="validation",
        )

    project_id = etapa.project_id
    try:
        delete_regular_etapa(etapa)
        db.session.commit()
    except EtapaNaoEditavelError as exc:
        db.session.rollback()
        return _fail_nao_editavel(exc)
    except Exception:
        db.session.rollback()
        return fail("Erro ao excluir etapa.", status=422, code="validation")

    project = db.session.get(Project, project_id)
    total = project.total_workflow_etapas if project is not None else 0
    return ok({"deleted_id": etapa_id, "project_id": project_id, "total_etapas": total})


@main_bp.route("/api/etapas/<int:etapa_id>/update-field", methods=["POST"])
@api_login_required
def api_etapa_update_field(etapa_id: int) -> Response | tuple[Response, int]:
    """Edita um campo inline da etapa (envelope), reusando ``update_regular_field``.

    Campos aceitos: ``descricao``/``data_inicio``/``data_fim`` — ``responsavel``
    sai por aqui (só ``POST /api/etapas/<id>/responsaveis`` escreve responsáveis)
    e responde "Campo inválido.". Ao mudar ``data_inicio``, o serviço normaliza para dia útil e propaga o
    ajuste à ``data_fim`` da própria etapa (dias úteis, server-side) — o ``front``
    NUNCA recalcula. Reuniões Google são recusadas (Fase 6).

    Returns:
        Envelope ``{field, etapa, field_update}`` com o resultado do serviço (mesmo
        ``response_data`` da rota legada); 404/403; 422 validação.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
    if is_google_meeting_stage(etapa):
        return fail(
            "Nesta reunião o ajuste de datas passa pelo fluxo de calendário.",
            status=422,
            code="validation",
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    field = data.get("field")
    value = data.get("value")
    if field not in _REGULAR_FIELDS:
        return fail("Campo inválido.", status=422, code="validation")

    try:
        field_update = update_regular_field(etapa, field, value)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return fail(str(exc), status=422, code="validation")
    except Exception:
        db.session.rollback()
        return fail("Erro ao salvar a alteração.", status=422, code="validation")

    return ok(
        {
            "field": field,
            "field_update": field_update,
            "etapa": _etapa_payload(etapa),
        }
    )


@main_bp.route("/api/etapas/<int:etapa_id>/comentario", methods=["POST"])
@api_login_required
def api_etapa_comentario(etapa_id: int) -> Response | tuple[Response, int]:
    """Salva/atualiza o comentário da etapa (envelope), reusando ``save_etapa_comentario``.

    Mesmas regras da rota legada: reuniões Google e etapas concluídas recusam
    edição de comentário.

    Returns:
        Envelope ``{message, etapa}``; 404/403; 422 validação.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
    if is_google_meeting_stage(etapa):
        return fail(
            "Reuniões Google não aceitam comentários de etapa.",
            status=422,
            code="validation",
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")
    comentario = (data.get("comentario") or "").strip()

    try:
        message = save_etapa_comentario(etapa, comentario)
        db.session.commit()
    except EtapaNaoEditavelError as exc:
        db.session.rollback()
        return _fail_nao_editavel(exc)
    except Exception:
        db.session.rollback()
        return fail("Erro ao salvar comentário.", status=422, code="validation")

    return ok({"message": message, "etapa": _etapa_payload(etapa)})


@main_bp.route("/api/etapas/<int:etapa_id>/responsaveis", methods=["POST"])
@api_login_required
def api_etapa_responsaveis(etapa_id: int) -> Response | tuple[Response, int]:
    """Substitui as áreas responsáveis da etapa (envelope), mudança #3.

    Corpo: ``{"areas": [{"area_id": 12, "label": "SES"}, {"area_id": null,
    "label": "Outras"}]}``. Reusa ``replace_etapa_responsaveis`` (substituição
    N:N + mirror legado ``etapa.responsavel``). Reuniões Google e etapas
    concluídas são recusadas.

    Returns:
        Envelope com a etapa atualizada; 404/403 de acesso; 422 validação.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
    if is_google_meeting_stage(etapa):
        return fail(
            "Reuniões do Google não têm áreas responsáveis editáveis.",
            status=422,
            code="validation",
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    areas = data.get("areas")
    if not isinstance(areas, list) or not areas:
        return fail(
            f"Pelo menos uma área responsável é obrigatória (recebido: {data.get('areas')!r}; "
            "esperado: lista não-vazia de objetos {area_id, label}).",
            status=422,
            code="validation",
        )

    try:
        replace_etapa_responsaveis(etapa, data["areas"])
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return fail(str(exc), status=422, code="validation")
    except Exception:
        db.session.rollback()
        return fail("Erro ao salvar responsáveis.", status=422, code="validation")

    return ok({"etapa": _etapa_payload(etapa)})


@main_bp.route("/api/etapas/<int:etapa_id>/toggle-iniciada", methods=["POST"])
@api_login_required
def api_etapa_toggle_iniciada(etapa_id: int) -> Response | tuple[Response, int]:
    """Alterna ``iniciada`` da etapa (envelope), espelhando ``toggle_iniciada_etapa``.

    Desmarcar ``iniciada`` também desmarca ``done`` (mesma regra legada).
    Reuniões Google são recusadas.

    Returns:
        Envelope com a etapa atualizada; 404/403; 422.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
    blocked = _etapa_editavel_ou_422(etapa, allow_done=True)
    if blocked is not None:
        return blocked
    if is_google_meeting_stage(etapa):
        return fail(
            "Reuniões Google não participam do fluxo de início/conclusão.",
            status=422,
            code="validation",
        )

    etapa.iniciada = not etapa.iniciada
    status_text = "iniciada" if etapa.iniciada else "não iniciada"
    log_project_action(
        project_id=etapa.project_id,
        action_type="toggle_iniciada",
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}',
    )
    if not etapa.iniciada and etapa.done:
        etapa.done = False
    db.session.commit()
    return ok({"etapa": _etapa_payload(etapa)})


@main_bp.route("/api/etapas/<int:etapa_id>/toggle", methods=["POST"])
@api_login_required
def api_etapa_toggle(etapa_id: int) -> Response | tuple[Response, int]:
    """Alterna ``done`` da etapa (envelope), espelhando ``toggle_etapa``.

    Bloqueia concluir etapa não iniciada, sem datas de início/término, sem área
    responsável (etapas importadas de modelo nascem sem) ou com tarefas abertas
    — todas 422 via ``motivo_bloqueio_conclusao``. Reuniões Google recusadas.

    Returns:
        Envelope com a etapa atualizada; 404/403; 422 com a regra violada.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
    blocked = _etapa_editavel_ou_422(etapa, allow_done=True)
    if blocked is not None:
        return blocked
    if is_google_meeting_stage(etapa):
        return fail(
            "Reuniões Google não participam do fluxo de início/conclusão.",
            status=422,
            code="validation",
        )

    if not etapa.iniciada and not etapa.done:
        return fail(
            "Não é possível concluir uma etapa que não foi iniciada.",
            status=422,
            code="validation",
        )
    if not etapa.done:
        motivo = motivo_bloqueio_conclusao(
            data_inicio=etapa.data_inicio,
            data_fim=etapa.data_fim,
            tem_responsavel=etapa_tem_responsavel(etapa),
            tarefas_abertas=count_open_tasks_in_etapa(etapa.id),
        )
        if motivo is not None:
            return fail(motivo, status=422, code="validation")

    etapa.done = not etapa.done
    status_text = "concluída" if etapa.done else "não concluída"
    log_project_action(
        project_id=etapa.project_id,
        action_type="toggle_done",
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}',
    )
    db.session.commit()
    return ok({"etapa": _etapa_payload(etapa)})


@main_bp.route("/api/projetos/<int:project_id>/etapas/reordenar", methods=["POST"])
@api_login_required
def api_etapas_reordenar(project_id: int) -> Response | tuple[Response, int]:
    """Reordena as etapas e DISPARA a cascata de datas (server-side).

    Persiste a nova ordem (``etapa_ids`` na ordem desejada) e, quando o corpo
    informa ``etapa_id``/``days_diff``, reusa ``cascade_subsequent_dates`` para
    deslocar as datas das etapas subsequentes em dias úteis — server-side. O
    front NÃO recalcula datas: o endpoint RE-BUSCA e devolve as etapas
    atualizadas para re-renderização.

    Returns:
        Envelope ``{etapas: [...]}`` com o estado atualizado; 404/403; 422.
    """
    project, error = _load_project_or_error(project_id)
    if error is not None:
        return error
    blocked = _projeto_editavel_ou_422(project)
    if blocked is not None:
        return blocked

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    etapa_ids = data.get("etapa_ids")
    if not isinstance(etapa_ids, list) or not etapa_ids:
        return fail("Lista de IDs de etapas inválida.", status=422, code="validation")

    try:
        ids_int = [int(eid) for eid in etapa_ids]
    except (TypeError, ValueError):
        return fail("Lista de IDs de etapas inválida.", status=422, code="validation")

    cascade_info, cascade_error = _resolve_cascade_request(project_id, data)
    if cascade_error is not None:
        return cascade_error

    try:
        _renumber_etapas_pinning_meetings(project, ids_int)

        if cascade_info is not None:
            _stale_ordem, days_diff = cascade_info
            # A ordem-base deve refletir o layout RESULTANTE pós-reorder (ver
            # docs/analise-testes-falhando.md §2.7); após a renumeração acima, a
            # própria ``ordem`` da etapa base já é essa posição.
            base_etapa = db.session.get(Etapa, int(data["etapa_id"]))
            base_ordem = base_etapa.ordem if base_etapa is not None else _stale_ordem
            cascade_subsequent_dates(project_id, base_ordem, days_diff)

        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao reordenar etapas.", status=422, code="validation")

    return ok({"etapas": _ordered_etapas_payload(project)})


def _renumber_etapas_pinning_meetings(project: Project, ids_int: list[int]) -> None:
    """Renumera TODAS as etapas 0..n-1 pinando as reuniões Google no rank atual.

    As reuniões mantêm a POSIÇÃO relativa (rank entre as etapas ordenadas), não o
    valor bruto de ``ordem`` — congelar o valor colidiria com a renumeração
    compactada das demais e o empate seria resolvido arbitrariamente pelo banco
    (bug 2.17 da auditoria; mesma semântica do teclado/DnD do front). As etapas
    regulares seguem a sequência do payload; ausentes vão para o fim na ordem
    atual, mantendo a renumeração self-healing após deleções.
    """
    atuais = (
        Etapa.query.filter_by(project_id=project.id)
        .order_by(Etapa.ordem.asc(), Etapa.id.asc())
        .all()
    )
    por_id = {etapa.id: etapa for etapa in atuais}
    reunioes_por_rank = {
        rank: etapa
        for rank, etapa in enumerate(atuais)
        if is_google_meeting_stage(etapa)
    }

    enviadas: list[Etapa] = []
    vistos: set[int] = set()
    for eid in ids_int:
        etapa = por_id.get(eid)
        if etapa is None or is_google_meeting_stage(etapa) or eid in vistos:
            continue
        vistos.add(eid)
        enviadas.append(etapa)
    faltantes = [
        etapa
        for etapa in atuais
        if not is_google_meeting_stage(etapa) and etapa.id not in vistos
    ]

    fila_regulares = iter(enviadas + faltantes)
    for rank in range(len(atuais)):
        etapa = reunioes_por_rank.get(rank)
        if etapa is None:
            etapa = next(fila_regulares)
        etapa.ordem = rank


def _resolve_cascade_request(
    project_id: int, data: dict[str, Any]
) -> tuple[tuple[int, int] | None, Any]:
    """Valida o pedido opcional de cascata embutido na reordenação/cascade.

    Returns:
        ``((base_ordem, days_diff), None)`` quando há cascata válida;
        ``(None, None)`` quando não há cascata; ``(None, fail_response)`` em erro.
    """
    base_etapa_id = data.get("etapa_id")
    days_diff = data.get("days_diff")
    if base_etapa_id is None or days_diff is None:
        return None, None

    try:
        days_diff = int(days_diff)
    except (TypeError, ValueError):
        return None, fail("Parâmetro de dias inválido.", status=422, code="validation")
    if abs(days_diff) > MAX_CASCADE_BUSINESS_DAYS:
        return None, fail(
            "A cascata de datas aceita no máximo "
            f"{MAX_CASCADE_BUSINESS_DAYS} dias úteis por operação.",
            status=422,
            code="validation",
        )

    base_etapa = db.session.get(Etapa, base_etapa_id)
    if base_etapa is None or base_etapa.project_id != project_id:
        return None, fail_not_found()
    if is_google_meeting_stage(base_etapa):
        return None, fail(
            "Reuniões Google não participam da cascata de datas.",
            status=422,
            code="validation",
        )
    return (base_etapa.ordem, days_diff), None


@main_bp.route("/api/projetos/<int:project_id>/cascade", methods=["POST"])
@api_login_required
def api_projeto_cascade(project_id: int) -> Response | tuple[Response, int]:
    """Recalcula datas em cascata (server-side), espelhando ``cascade_date_update``.

    Reusa ``cascade_subsequent_dates``: desloca as datas das etapas após a etapa
    base (``etapa_id``) em ``days_diff`` dias úteis. RE-BUSCA e devolve as etapas
    atualizadas — o front NÃO recalcula datas.

    Returns:
        Envelope ``{etapas: [...]}``; 404/403; 422 validação.
    """
    project, error = _load_project_or_error(project_id)
    if error is not None:
        return error
    blocked = _projeto_editavel_ou_422(project)
    if blocked is not None:
        return blocked

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")
    if data.get("etapa_id") is None or data.get("days_diff") is None:
        return fail("Parâmetros inválidos.", status=422, code="validation")

    cascade_info, cascade_error = _resolve_cascade_request(project_id, data)
    if cascade_error is not None:
        return cascade_error

    try:
        base_ordem, days_diff = cascade_info
        cascade_subsequent_dates(project_id, base_ordem, days_diff)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail(
            "Erro ao atualizar datas subsequentes.", status=422, code="validation"
        )

    return ok({"etapas": _ordered_etapas_payload(project)})


def _stage_templates_payload() -> list[dict[str, Any]]:
    """Lista os modelos de etapas com contadores (mesma forma do legado).

    Reproduz a query/serialização de ``get_templates`` (``GET /api/templates`` em
    ``routes/api/legacy.py``): para cada ``StageTemplate``, o número de etapas e a
    soma das durações em dias. Mantém os mesmos campos/ordenação para que o
    frontend (``fetchStageTemplates``) consuma sem recalcular.

    Returns:
        Lista de ``{"id", "name", "stage_count", "total_duration_days"}``,
        ordenada por ``name``.
    """
    stats_rows = (
        db.session.query(
            StageTemplateItem.templateId,
            func.count(StageTemplateItem.id),
            func.coalesce(func.sum(StageTemplateItem.duration_days), 0),
        )
        .group_by(StageTemplateItem.templateId)
        .all()
    )
    stats_by_template = {tid: (count, int(total)) for tid, count, total in stats_rows}

    payload: list[dict[str, Any]] = []
    for template in StageTemplate.query.order_by(StageTemplate.name).all():
        count, total = stats_by_template.get(template.id, (0, 0))
        payload.append(
            {
                "id": template.id,
                "name": template.name,
                "stage_count": count,
                "total_duration_days": total,
            }
        )
    return payload


@main_bp.route("/api/etapas/templates", methods=["GET"])
@api_login_required
def api_etapas_templates() -> Response | tuple[Response, int]:
    """Lista os modelos de etapas no envelope canônico (para o modal de importação).

    Espelho enveloped do legado ``GET /api/templates`` (que devolve array cru e
    HTML em 401): reusa a MESMA query/serialização (``_stage_templates_payload``)
    e devolve ``ok([...])`` com ``api_login_required`` (401 JSON). O legado
    permanece intacto (strangler).

    Returns:
        Envelope ``{"ok": true, "data": [{"id", "name", "stage_count",
        "total_duration_days"}, ...]}`` com HTTP 200; 401 JSON sem sessão.
    """
    return ok(_stage_templates_payload())


@main_bp.route("/api/projetos/<int:project_id>/importar-modelo", methods=["POST"])
@api_login_required
def api_projeto_importar_modelo(project_id: int) -> Response | tuple[Response, int]:
    """Aplica um modelo de etapas ao projeto (envelope), reusando ``import_template_stages``.

    Mesma regra da rota Jinja ``import_model_to_project``: cria as etapas do
    modelo em sequência a partir de ``start_date`` (corpo: ``template_id``,
    ``start_date`` em ``YYYY-MM-DD``), registra histórico e a ``StageTemplateUsage``.

    Returns:
        Envelope ``{etapas_criadas, etapas: [...]}``; 404 (projeto/modelo) / 403;
        422 validação.
    """
    project, error = _load_project_or_error(project_id)
    if error is not None:
        return error

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    template_id = data.get("template_id")
    start_date_str = data.get("start_date")
    if not template_id or not start_date_str:
        return fail(
            "Selecione um modelo e defina a data de início.",
            status=422,
            code="validation",
        )

    start_date, ok_date = _parse_date(start_date_str)
    if not ok_date or start_date is None:
        return fail("Formato de data inválido.", status=422, code="validation")

    template = db.session.get(StageTemplate, template_id)
    if template is None:
        return fail_not_found()
    if not template.items:
        return fail("Este modelo não possui etapas.", status=422, code="validation")

    try:
        etapas_criadas = import_template_stages(
            project,
            template,
            start_date,
            created_by_id=g.user.id if g.user else None,
            source="post_import",
        )
        db.session.commit()
    except EtapaNaoEditavelError as exc:
        db.session.rollback()
        return _fail_nao_editavel(exc)
    except Exception:
        db.session.rollback()
        return fail("Erro ao importar modelo.", status=422, code="validation")

    return ok(
        {
            "etapas_criadas": etapas_criadas,
            "etapas": _ordered_etapas_payload(project),
        }
    )
