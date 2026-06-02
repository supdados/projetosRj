"""Endpoints JSON de MUTAÇÃO de projetos (criar / concluir) + catálogos auxiliares.

Cobre as features de paridade da SPA que faltavam no envelope canônico:

    - ``POST /api/projetos``                       — cria projeto (Quick Create).
    - ``POST /api/projetos/<id>/concluir``         — conclui projeto (celebração).
    - ``GET  /api/catalogos/objetivos``            — catálogo de objetivos EEGD
      (o select inicial do modal; resultados/indicadores já vêm dos legados
      ``/api/resultados/<id>`` e ``/api/indicadores/<id>``).
    - ``GET  /api/projetos/<pid>/etapas/<eid>/tarefas`` — tarefas de uma etapa
      (substitui o HTML de ``project_stage_tasks_panel`` para o quick-add).

REUSO sem duplicar regra:
    - Criação: ``services/project_creation.py`` (mesma lógica de ``add_project``).
    - Conclusão: ``services/project_completion.py`` (mesmas 3 validações de
      ``concluir_project``).
    - Órgão: ``routes/projects/crud._resolve_orgao_from_form`` (mesma validação
      de escopo do form Jinja).
    - Permissão de leitura/escopo: ``user_can_access_project``.

Anexa ao ``main_bp`` ÚNICO; NÃO cria blueprint novo e NÃO altera as rotas Jinja.
"""

from __future__ import annotations

import datetime
from typing import Any

from flask import Response, g, request, session

from catalogs.abep import normalize_abep_indicator
from catalogs.objectives import (
    get_objetivos_choices,
    normalize_goal_selection,
)
from models import Etapa, Project, Task, db

from ..blueprint import main_bp
from ..orgao_scope import user_can_access_project
from ..projects.crud import _resolve_orgao_from_form
from ..shared import log_project_action
from ..tasks.permissions import task_permission_flags
from .envelope import fail, ok
from .negotiation import api_login_required
from .serializers import serialize_project_card, serialize_task_card
from services.project_completion import ProjectCompletionError, complete_project
from services.project_creation import (
    ProjectCreationInput,
    StageDraft,
    create_project_record,
)


def _coerce_int(value: Any) -> int | None:
    """Converte ``value`` para ``int`` aceitando string; ``None`` se inválido."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_creation_etapas(raw: Any) -> list[StageDraft]:
    """Converte ``etapas[]`` JSON em ``StageDraft`` (descricao + duration)."""
    if not isinstance(raw, list):
        return []
    drafts: list[StageDraft] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        drafts.append(
            StageDraft(
                descricao=(item.get("descricao") or "").strip(),
                duration_days=_coerce_int(item.get("duration")),
            )
        )
    return drafts


@main_bp.route("/api/projetos", methods=["POST"])
@api_login_required
def api_projeto_criar() -> Response | tuple[Response, int]:
    """Cria um projeto (Quick Create) no envelope, reusando ``add_project``.

    Body JSON espelha o form: ``titulo`` (req), ``orgao_id`` (req, validado via
    ``_resolve_orgao_from_form`` contra o escopo do usuário), ``orgao``,
    ``prioridade``, ``objetivo``/``resultado``/``indicadores[]``, ``observacao``,
    ``special_project``, ``sei_process``, ``short_description``,
    ``delivery_type``, ``abep_indicator``, ``github_link``,
    ``documentation_link``, ``product_link``, ``etapas[]{descricao,duration}``,
    ``start_date`` (``YYYY-MM-DD``), ``template_id``.

    Returns:
        ``ok({id, redirect_to, message})`` (200); 422 validação; 403 órgão fora
        do escopo; 401 sem sessão.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    titulo = (data.get("titulo") or "").strip()
    if not titulo:
        return fail("O título do projeto é obrigatório.", status=422, code="validation")

    orgao_unidade, orgao_error = _resolve_orgao_from_form(data.get("orgao_id"))
    if orgao_error:
        # Órgão fora do escopo => 403; ausente/ inexistente => 422.
        is_forbidden = "permissão" in orgao_error.lower()
        return fail(
            orgao_error,
            status=403 if is_forbidden else 422,
            code="forbidden" if is_forbidden else "validation",
        )

    try:
        objetivo_id, resultado_id, indicador_ids = normalize_goal_selection(
            data.get("objetivo"),
            data.get("resultado"),
            data.get("indicadores") or [],
        )
    except ValueError as exc:
        return fail(str(exc), status=422, code="validation")

    start_date = None
    start_raw = data.get("start_date")
    if start_raw:
        try:
            start_date = datetime.datetime.strptime(start_raw, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return fail("Formato de data inválido.", status=422, code="validation")

    creation_input = ProjectCreationInput(
        titulo=titulo,
        orgao_unidade=orgao_unidade,
        orgao=data.get("orgao") or None,
        prioridade=data.get("prioridade") or None,
        objetivo_id=objetivo_id,
        resultado_esperado_id=resultado_id,
        indicador_ids=indicador_ids,
        observacao=data.get("observacao") or None,
        special_project=data.get("special_project") or None,
        sei_process=data.get("sei_process") or None,
        short_description=data.get("short_description") or None,
        delivery_type=data.get("delivery_type") or None,
        abep_indicator=normalize_abep_indicator(data.get("abep_indicator")),
        github_link=data.get("github_link") or None,
        documentation_link=data.get("documentation_link") or None,
        product_link=data.get("product_link") or None,
        etapas=_parse_creation_etapas(data.get("etapas")),
        start_date=start_date,
        template_id=_coerce_int(data.get("template_id")),
        is_tutorial=bool(
            session.get("tutorial_active") and not session.get("tutorial_project_id")
        ),
    )

    try:
        new_project = create_project_record(
            creation_input, created_by_id=g.user.id if g.user else None
        )
        log_project_action(
            project_id=new_project.id,
            action_type="create",
            description=f'Criou o projeto "{titulo}"',
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return fail(str(exc), status=422, code="validation")
    except Exception as exc:
        db.session.rollback()
        return fail(
            f"Ocorreu um erro ao adicionar o projeto: {exc}",
            status=500,
            code="server",
        )

    if session.get("tutorial_active"):
        session["tutorial_project_id"] = new_project.id

    return ok(
        {
            "id": new_project.id,
            "redirect_to": f"/projetos/{new_project.id}",
            "message": "Projeto adicionado com sucesso!",
            "project": serialize_project_card(new_project),
        }
    )


@main_bp.route("/api/projetos/<int:project_id>/concluir", methods=["POST"])
@api_login_required
def api_projeto_concluir(project_id: int) -> Response | tuple[Response, int]:
    """Conclui um projeto (envelope), reusando ``complete_project``.

    Replica as 3 validações de ``concluir_project`` (permissão 403, status
    Vigente 400, todas as etapas concluídas 400). Em sucesso devolve a mensagem
    de celebração e ``redirect_to`` apontando para a rota SPA do detalhe (não o
    Jinja) — o front toca o chime + confetes + overlay e navega via router.

    Returns:
        ``ok({message, redirect_to, status})`` (200); 403/400 com a mensagem e a
        categoria de flash equivalentes ao legado; 404 projeto inexistente; 401.
    """
    project = db.session.get(Project, project_id)
    if project is None:
        return fail("Projeto não encontrado.", status=404, code="not_found")

    try:
        complete_project(project, g.user)
        db.session.commit()
    except ProjectCompletionError as exc:
        db.session.rollback()
        code = "forbidden" if exc.status == 403 else "validation"
        return fail(exc.message, status=exc.status, code=code)
    except Exception:
        db.session.rollback()
        return fail(
            "Erro ao concluir projeto. Tente novamente em instantes.",
            status=500,
            code="server",
        )

    return ok(
        {
            "message": f'Projeto "{project.titulo}" foi concluído com sucesso!',
            "redirect_to": f"/projetos/{project.id}",
            "status": "Finalizado",
        }
    )


@main_bp.route("/api/catalogos/objetivos", methods=["GET"])
@api_login_required
def api_catalogo_objetivos() -> Response | tuple[Response, int]:
    """Catálogo de objetivos EEGD para o select inicial do modal de criação.

    Envelope-wrapper de ``get_objetivos_choices`` (a mesma fonte que o Jinja
    injeta via ``render_template``). Resultados/indicadores continuam nos legados
    ``/api/resultados/<id>`` e ``/api/indicadores/<id>``.

    Returns:
        ``ok([{id, descricao}, ...])`` (200); 401 sem sessão.
    """
    return ok(get_objetivos_choices())


def _stage_task_card(task: Task) -> dict[str, Any]:
    """Card de tarefa de etapa, acrescentando contadores e flags completos.

    Reusa ``serialize_task_card`` e enriquece com ``comments_count``/
    ``anexos_count``/``can_delete``/``is_author`` (úteis ao quick-add), derivados
    de ``task_permission_flags`` (mesma fonte autoritativa).
    """
    card = serialize_task_card(task)
    flags = task_permission_flags(task)
    card["comments_count"] = len(task.comments)
    card["anexos_count"] = len(task.anexos)
    card["permissions"]["can_delete"] = bool(flags["can_delete"])
    card["permissions"]["is_author"] = bool(flags["is_author"])
    return card


@main_bp.route(
    "/api/projetos/<int:project_id>/etapas/<int:etapa_id>/tarefas", methods=["GET"]
)
@api_login_required
def api_etapa_tarefas(
    project_id: int, etapa_id: int
) -> Response | tuple[Response, int]:
    """Lista as tarefas (não arquivadas) de uma etapa no envelope (quick-add).

    Substitui o HTML de ``project_stage_tasks_panel`` por dados serializados.
    Valida escopo via ``user_can_access_project`` e que a etapa pertence ao
    projeto.

    Returns:
        ``ok({tarefas: [...], total, done})`` (200); 404 projeto/etapa; 403; 401.
    """
    project = db.session.get(Project, project_id)
    if project is None:
        return fail("Projeto não encontrado.", status=404, code="not_found")
    if not user_can_access_project(g.user, project):
        return fail(
            "Você não tem permissão para acessar este projeto.",
            status=403,
            code="forbidden",
        )

    etapa = db.session.get(Etapa, etapa_id)
    if etapa is None or etapa.project_id != project.id:
        return fail("Etapa não encontrada.", status=404, code="not_found")

    tarefas = (
        Task.query.filter(
            Task.project_id == project.id,
            Task.etapa_id == etapa.id,
            Task.is_archived.is_(False),
        )
        .order_by(Task.ordem.asc(), Task.created_at.asc(), Task.id.asc())
        .all()
    )
    done = sum(1 for t in tarefas if t.status == "finalizada")
    return ok(
        {
            "tarefas": [_stage_task_card(task) for task in tarefas],
            "total": len(tarefas),
            "done": done,
        }
    )
