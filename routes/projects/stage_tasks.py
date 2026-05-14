"""Endpoints AJAX para o modal de tarefas por etapa na página do projeto."""

from flask import g, jsonify, render_template, request

from sqlalchemy.orm import selectinload

from models import Etapa, Project, Task, TaskComment

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.orgao_scope import user_can_access_project
from routes.shared import get_or_404
from routes.tasks.permissions import task_permission_flags

# Limite por requisição. UIs paginadas devem passar `limit` + `offset`.
STAGE_TASKS_PANEL_LIMIT = 50
STAGE_TASKS_PANEL_MAX = 100


def _task_query_for_stage(project, stage_id):
    return (
        Task.query.options(
            selectinload(Task.comments).selectinload(TaskComment.author),
            selectinload(Task.anexos),
        )
        .filter(
            Task.project_id == project.id,
            Task.etapa_id == stage_id,
            Task.is_archived.is_(False),
        )
        .order_by(Task.ordem.asc(), Task.created_at.asc(), Task.id.asc())
    )


def _parse_pagination():
    raw_limit = request.args.get("limit", STAGE_TASKS_PANEL_LIMIT, type=int)
    limit = min(max(raw_limit or STAGE_TASKS_PANEL_LIMIT, 1), STAGE_TASKS_PANEL_MAX)
    offset = max(request.args.get("offset", 0, type=int) or 0, 0)
    return limit, offset


@main_bp.route("/project/<int:project_id>/etapa/<int:etapa_id>/tasks", methods=["GET"])
@login_required
def project_stage_tasks_panel(project_id, etapa_id):
    """Retorna o HTML da lista de tarefas de uma etapa específica.

    Não inclui tarefas legadas (etapa_id NULL) — essas vivem no endpoint
    `project_legacy_tasks_panel` para evitar duplicar a lista em todo modal.
    """
    project = get_or_404(Project, project_id)
    if not user_can_access_project(g.user, project):
        return jsonify({"success": False, "message": "Sem permissão."}), 403

    etapa = get_or_404(Etapa, etapa_id)
    if etapa.project_id != project.id:
        return jsonify({"success": False, "message": "Etapa inválida."}), 404

    limit, offset = _parse_pagination()
    page = _task_query_for_stage(project, etapa.id).offset(offset).limit(limit + 1).all()
    stage_has_more = len(page) > limit
    stage_tasks = page[:limit]

    permission_flags_by_task_id = {
        task.id: task_permission_flags(task) for task in stage_tasks
    }

    html = render_template(
        "projects/_stage_tasks_panel.html",
        project=project,
        etapa=etapa,
        stage_tasks=stage_tasks,
        stage_has_more=stage_has_more,
        limit=limit,
        offset=offset,
        permission_flags_by_task_id=permission_flags_by_task_id,
    )
    return jsonify(
        {
            "success": True,
            "html": html,
            "stage_count": len(stage_tasks),
            "stage_has_more": stage_has_more,
        }
    )


@main_bp.route("/project/<int:project_id>/tarefas-sem-etapa", methods=["GET"])
@login_required
def project_legacy_tasks_panel(project_id):
    """Lista de tarefas do projeto sem etapa associada (legado).

    Endpoint próprio para que o modal de cada etapa não duplique a lista de
    legadas — chamado por um botão dedicado "Tarefas sem etapa".
    """
    project = get_or_404(Project, project_id)
    if not user_can_access_project(g.user, project):
        return jsonify({"success": False, "message": "Sem permissão."}), 403

    limit, offset = _parse_pagination()
    page = _task_query_for_stage(project, None).offset(offset).limit(limit + 1).all()
    legacy_has_more = len(page) > limit
    legacy_tasks = page[:limit]

    permission_flags_by_task_id = {
        task.id: task_permission_flags(task) for task in legacy_tasks
    }

    html = render_template(
        "projects/_legacy_tasks_panel.html",
        project=project,
        legacy_tasks=legacy_tasks,
        legacy_has_more=legacy_has_more,
        limit=limit,
        offset=offset,
        permission_flags_by_task_id=permission_flags_by_task_id,
    )
    return jsonify(
        {
            "success": True,
            "html": html,
            "legacy_count": len(legacy_tasks),
            "legacy_has_more": legacy_has_more,
        }
    )
