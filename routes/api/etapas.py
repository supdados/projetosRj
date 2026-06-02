"""Endpoints JSON de mutação de ETAPAS (Fase 5a) consumidos pela SPA.

Cobre o CRUD de etapas, edição inline de campos (com cascata de datas
server-side), comentários, toggles de iniciada/concluída, reordenação (que
dispara a cascata de datas) e a importação de um modelo de etapas para o
projeto. TODOS no envelope canônico (``ok``/``fail``), protegidos por
``api_login_required`` (401 JSON) e por ``user_can_access_project`` — via o
projeto da etapa — (404 inexistente / 403 fora de escopo).

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
from services.etapas_cascade import cascade_subsequent_dates
from services.etapas_import import import_template_stages
from services.etapas_mutation import (
    count_open_tasks_in_etapa,
    create_etapa_record,
    delete_regular_etapa,
    save_etapa_comentario,
    update_regular_field,
)
from services.project_meetings import is_google_meeting_stage

from ..blueprint import main_bp
from ..orgao_scope import user_can_access_project
from ..shared import log_project_action
from .envelope import fail, ok
from .negotiation import api_login_required
from .serializers import serialize_etapa_detail, serialize_project_detail

MAX_CASCADE_BUSINESS_DAYS = 365
_REGULAR_FIELDS = {"descricao", "data_inicio", "data_fim", "responsavel"}


# ── Carregamento + escopo ─────────────────────────────────────────────────────


def _load_project_or_error(project_id: int) -> tuple[Project | None, Any]:
    """Carrega o projeto validando existência (404) e escopo de órgão (403)."""
    project = db.session.get(Project, project_id)
    if project is None:
        return None, fail("Projeto não encontrado.", status=404, code="not_found")
    if not user_can_access_project(g.user, project):
        return None, fail(
            "Você não tem permissão para acessar este projeto.",
            status=403,
            code="forbidden",
        )
    return project, None


def _load_etapa_or_error(etapa_id: int) -> tuple[Etapa | None, Any]:
    """Carrega a etapa validando existência (404) e escopo via projeto (403)."""
    etapa = db.session.get(Etapa, etapa_id)
    if etapa is None:
        return None, fail("Etapa não encontrada.", status=404, code="not_found")
    if not user_can_access_project(g.user, etapa.project):
        return None, fail(
            "Você não tem permissão para alterar etapas deste projeto.",
            status=403,
            code="forbidden",
        )
    return etapa, None


# ── Serialização ──────────────────────────────────────────────────────────────


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


# ── CRUD ──────────────────────────────────────────────────────────────────────


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
        return fail("A descrição da etapa é obrigatória.", status=422, code="validation")

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
            responsavel=(data.get("responsavel") or "").strip() or None,
            comentarios=(data.get("comentarios") or "").strip() or None,
            iniciada=iniciada,
            done=done,
        )
        db.session.commit()
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


@main_bp.route("/api/etapas/<int:etapa_id>", methods=["POST"])
@api_login_required
def api_etapa_edit(etapa_id: int) -> Response | tuple[Response, int]:
    """Edita uma etapa regular (envelope), espelhando o POST de ``edit_etapa``.

    Atualiza descrição/responsável/comentários/datas/iniciada/done com as mesmas
    regras: concluir exige iniciada e nenhuma tarefa aberta. Reuniões Google são
    recusadas (Fase 6). Datas em ``YYYY-MM-DD``.

    Returns:
        Envelope com a etapa atualizada; 404/403 de acesso; 422 validação.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
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

    iniciada = bool(data.get("iniciada"))
    done_requested = bool(data.get("done"))

    if not iniciada and done_requested:
        return fail(
            "A etapa não pode ser concluída sem ser iniciada.",
            status=422,
            code="validation",
        )
    if done_requested and not etapa.done:
        open_count = count_open_tasks_in_etapa(etapa.id)
        if open_count:
            return fail(
                f"Finalize as {open_count} tarefa(s) pendente(s) antes de concluir.",
                status=422,
                code="validation",
            )

    old_descricao = etapa.descricao
    etapa.descricao = data.get("descricao")
    etapa.responsavel = data.get("responsavel")
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
    except Exception:
        db.session.rollback()
        return fail("Erro ao excluir etapa.", status=422, code="validation")

    project = db.session.get(Project, project_id)
    total = project.total_workflow_etapas if project is not None else 0
    return ok({"deleted_id": etapa_id, "project_id": project_id, "total_etapas": total})


# ── Edição inline de campo (cascata server-side) ──────────────────────────────


@main_bp.route("/api/etapas/<int:etapa_id>/update-field", methods=["POST"])
@api_login_required
def api_etapa_update_field(etapa_id: int) -> Response | tuple[Response, int]:
    """Edita um campo inline da etapa (envelope), reusando ``update_regular_field``.

    Campos aceitos: ``descricao``/``data_inicio``/``data_fim``/``responsavel``.
    Ao mudar ``data_inicio``, o serviço normaliza para dia útil e propaga o
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
    except ValueError:
        db.session.rollback()
        return fail("Formato de data inválido.", status=422, code="validation")
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


# ── Comentário ────────────────────────────────────────────────────────────────


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
    if etapa.done:
        return fail(
            "Não é possível editar comentários de uma etapa concluída.",
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
    except Exception:
        db.session.rollback()
        return fail("Erro ao salvar comentário.", status=422, code="validation")

    return ok({"message": message, "etapa": _etapa_payload(etapa)})


# ── Toggles ───────────────────────────────────────────────────────────────────


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

    Bloqueia concluir etapa não iniciada (422) e etapa com tarefas abertas (422,
    ``open_task_count``). Reuniões Google são recusadas.

    Returns:
        Envelope com a etapa atualizada; 404/403; 422 com a regra violada.
    """
    etapa, error = _load_etapa_or_error(etapa_id)
    if error is not None:
        return error
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
        open_count = count_open_tasks_in_etapa(etapa.id)
        if open_count:
            return fail(
                f"Finalize as {open_count} tarefa(s) pendente(s) desta etapa antes de concluí-la.",
                status=422,
                code="validation",
            )

    etapa.done = not etapa.done
    status_text = "concluída" if etapa.done else "não concluída"
    log_project_action(
        project_id=etapa.project_id,
        action_type="toggle_done",
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}',
    )
    db.session.commit()
    return ok({"etapa": _etapa_payload(etapa)})


# ── Reordenação + cascata ─────────────────────────────────────────────────────


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
        for index, eid in enumerate(ids_int):
            etapa = Etapa.query.filter_by(id=eid, project_id=project.id).first()
            if etapa is not None:
                etapa.ordem = index

        if cascade_info is not None:
            _stale_ordem, days_diff = cascade_info
            # A ordem-base deve refletir o layout RESULTANTE pós-reorder; usar a
            # posição do ID base na lista reordenada (ids_int) evita cascatear
            # sobre a ordem antiga já lida por _resolve_cascade_request (ver
            # docs/analise-testes-falhando.md §2.7).
            base_etapa_id = int(data["etapa_id"])
            base_ordem = (
                ids_int.index(base_etapa_id)
                if base_etapa_id in ids_int
                else _stale_ordem
            )
            cascade_subsequent_dates(project_id, base_ordem, days_diff)

        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao reordenar etapas.", status=422, code="validation")

    return ok({"etapas": _ordered_etapas_payload(project)})


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
        return None, fail("Etapa base não encontrada.", status=404, code="not_found")
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


# ── Modelos de etapas (listagem para o modal de importação) ───────────────────


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


# ── Importar modelo ───────────────────────────────────────────────────────────


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
        return fail("Modelo não encontrado.", status=404, code="not_found")
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
    except Exception:
        db.session.rollback()
        return fail("Erro ao importar modelo.", status=422, code="validation")

    return ok(
        {
            "etapas_criadas": etapas_criadas,
            "etapas": _ordered_etapas_payload(project),
        }
    )
