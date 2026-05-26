from flask import flash, g, jsonify, redirect, url_for

from models import (
    Etapa,
    LegacyTaskRedirect,
    Project,
    Task,
    db,
)

from routes.blueprint import main_bp
from routes.decorators import login_required

from routes.tasks.helpers import (
    _build_legacy_query_args,
    _can_access_project_in_tasks,
    _can_view_task,
    _render_task_hub,
)


@main_bp.route("/tarefas", methods=["GET"])
@login_required
def list_tasks():
    return _render_task_hub()


@main_bp.route("/tarefas/arquivadas", methods=["GET"])
@login_required
def list_tasks_archived():
    return _render_task_hub(include_archived=True)


@main_bp.route("/tarefas/finalizadas", methods=["GET"])
@login_required
def list_tasks_finalized():
    return redirect(
        f'{url_for("main.list_tasks_archived")}{_build_legacy_query_args()}'
    )


@main_bp.route("/tarefas/<int:task_id>", methods=["GET"])
@login_required
def task_detail(task_id):
    task = db.session.get(Task, task_id)

    if task and _can_view_task(g.user, task):
        if task.project_id:
            return redirect(
                url_for(
                    "main.project_tasks", project_id=task.project_id, focus_task=task.id
                )
            )
        return redirect(url_for("main.list_tasks", focus_task=task.id))

    legacy = LegacyTaskRedirect.query.filter_by(legacy_task_id=task_id).first()
    if legacy:
        if legacy.project_id:
            project = db.session.get(Project, legacy.project_id)
            if not project or not _can_access_project_in_tasks(project):
                flash("Tarefa não encontrada.", "warning")
                return redirect(url_for("main.list_tasks"))
            params = {}
            sample_task = (
                db.session.get(Task, legacy.sample_task_id)
                if legacy.sample_task_id
                else None
            )
            if sample_task and _can_view_task(g.user, sample_task):
                params["focus_task"] = legacy.sample_task_id
            return redirect(
                url_for("main.project_tasks", project_id=legacy.project_id, **params)
            )
        params = {}
        sample_task = (
            db.session.get(Task, legacy.sample_task_id) if legacy.sample_task_id else None
        )
        if sample_task and _can_view_task(g.user, sample_task):
            params["focus_task"] = legacy.sample_task_id
        return redirect(url_for("main.list_tasks", **params))

    flash("Tarefa não encontrada.", "warning")
    return redirect(url_for("main.list_tasks"))


@main_bp.route("/tarefas/projeto/<int:project_id>/etapas", methods=["GET"])
@login_required
def list_project_etapas(project_id):
    """Lista as etapas de um projeto para o seletor de criação de tarefa.

    Consumido pelo composer do kanban: ao escolher o projeto, o front busca aqui
    as etapas disponíveis para popular o campo "Etapa". Etapas concluídas vêm
    marcadas com ``done`` para que o front as exiba desabilitadas (regra de
    ``_resolve_etapa_token``: etapa concluída não aceita novas tarefas).

    Exemplo de resposta::

        {"success": true, "etapas": [{"value": "12", "label": "Diagnóstico",
                                      "done": false}]}
    """
    project = db.session.get(Project, project_id)
    if project is None:
        return jsonify({"success": False, "message": "Projeto não encontrado."}), 404

    if not _can_access_project_in_tasks(project):
        return (
            jsonify({"success": False, "message": "Sem permissão para este projeto."}),
            403,
        )

    etapas = (
        Etapa.query.filter(Etapa.project_id == project.id)
        .order_by(Etapa.ordem.asc(), Etapa.id.asc())
        .all()
    )
    return jsonify(
        {
            "success": True,
            "etapas": [
                {
                    "value": str(etapa.id),
                    "label": etapa.descricao or "Etapa sem descrição",
                    "done": bool(etapa.done),
                }
                for etapa in etapas
            ],
        }
    )


@main_bp.route("/projeto/<int:project_id>/tarefas", methods=["GET"])
@login_required
def project_tasks(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        flash("Projeto não encontrado.", "warning")
        return redirect(url_for("main.list_projects"))

    if not _can_access_project_in_tasks(project):
        flash("Você não tem permissão para acessar este projeto.", "danger")
        return redirect(url_for("main.list_projects"))

    return _render_task_hub(locked_project=project, template_name="projects/tasks.html")
