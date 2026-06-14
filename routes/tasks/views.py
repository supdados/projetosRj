from flask import flash, g, jsonify, redirect, request, url_for

from models import (
    Etapa,
    LegacyTaskRedirect,
    Project,
    Task,
    db,
)

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.orgao_scope import (
    redirect_to_current_route_without_orgao,
    sanitize_orgao_filter_for_current_user,
)
from routes.spa import _render_spa

from routes.tasks.helpers import (
    _build_legacy_query_args,
    _can_access_project_in_tasks,
    _can_view_task,
)
from routes.tasks.queries import _read_task_filter_values


def _serve_task_hub_spa_or_redirect():
    """Serve a shell da SPA do hub, preservando o redirect de orgao invalido.

    O hub legado redirecionava (302) sem o parametro de orgao quando o filtro
    era invalido para o usuario corrente. Preservamos esse contrato no path
    nativo (incluindo o alias legado ``?area=``, lido por
    ``_read_task_filter_values``) para nao quebrar a suite nem links existentes;
    nos demais casos servimos a SPA, cuja fonte de dados vive em
    ``GET /api/tarefas``.
    """
    filter_values = _read_task_filter_values(request.args)
    _, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        filter_values["orgao_filter"]
    )
    if invalid_orgao_filter:
        return redirect_to_current_route_without_orgao()
    return _render_spa()


@main_bp.route("/tarefas", methods=["GET"])
@login_required
def list_tasks():
    """Serve a SPA no path nativo ``/tarefas`` (cut-over KEEP-ENDPOINT).

    O endpoint ``main.list_tasks`` permanece para que o ``target_url``
    PERSISTIDO em notificacoes (``routes/tasks/notifications.py``) e os
    redirects de ``creation.py``/``crud.py`` continuem validos; uma notificacao
    antiga abre agora a SPA. A fonte de dados real do hub vive em
    ``GET /api/tarefas`` (consumido pela SPA).
    """
    return _serve_task_hub_spa_or_redirect()


@main_bp.route("/tarefas/arquivadas", methods=["GET"])
@login_required
def list_tasks_archived():
    """Redireciona (302) para ``/tarefas?modo=arquivadas`` (KEEP-ENDPOINT).

    O endpoint permanece registrado porque ``target_url`` PERSISTIDO em
    notificacoes (``routes/tasks/notifications.py``) e os redirects de
    ``crud.py``/``list_tasks_finalized`` apontam para ca. A SPA NAO possui rota
    client-side ``/tarefas/arquivadas`` — o modo "arquivadas" e estado da pagina
    ``/tarefas``, inicializado pelo query param ``modo`` (lido no mount).
    """
    query_args = request.args.to_dict(flat=True)
    query_args["modo"] = "arquivadas"
    return redirect(url_for("main.list_tasks", **query_args))


@main_bp.route("/tarefas/finalizadas", methods=["GET"])
@login_required
def list_tasks_finalized():
    """Mantem o redirect legado para ``/tarefas/arquivadas`` (302).

    Endpoint preservado (alguns redirects/links apontam para ``finalizadas``);
    o comportamento de redirecionar para a listagem de arquivadas e mantido para
    nao quebrar a suite nem links existentes.
    """
    return redirect(
        f'{url_for("main.list_tasks_archived")}{_build_legacy_query_args()}'
    )


@main_bp.route("/tarefas/<int:task_id>", methods=["GET"])
@login_required
def task_detail(task_id):
    """Resolve o deep-link de tarefa e redireciona (302) para a listagem da SPA.

    O endpoint ``main.task_detail`` permanece (a busca e ``queries.py`` emitem
    esse path). O comportamento de redirect e mantido: para tarefa visivel,
    redireciona para ``/projeto/<id>/tarefas`` ou ``/tarefas`` com ``focus_task``
    (a SPA cuida do foco); ``LegacyTaskRedirect`` segue resolvendo para o
    destino canonico.
    """
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
            db.session.get(Task, legacy.sample_task_id)
            if legacy.sample_task_id
            else None
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
    """Redireciona (302) para ``/tarefas?project=<id>`` (KEEP-ENDPOINT).

    Endpoint preservado (``task_detail`` redireciona para ele com ``focus_task``;
    notificacoes com ``target_url`` persistido e redirects apontam para ca). A
    SPA NAO possui rota client-side ``/projeto/<id>/tarefas``: o hub filtrado por
    projeto e a propria pagina ``/tarefas``, que le ``?project=`` (e o
    ``?focus_task=`` preservado aqui) no mount. Mantemos a checagem de
    existencia/permissao do projeto (302 para a Lista quando inacessivel).
    """
    project = db.session.get(Project, project_id)
    if not project:
        flash("Projeto não encontrado.", "warning")
        return redirect("/projetos")

    if not _can_access_project_in_tasks(project):
        flash("Você não tem permissão para acessar este projeto.", "danger")
        return redirect("/projetos")

    query_args = request.args.to_dict(flat=True)
    query_args["project"] = str(project_id)
    return redirect(url_for("main.list_tasks", **query_args))
