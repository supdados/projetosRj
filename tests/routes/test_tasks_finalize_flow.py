import time

from models import Task, TaskAccessAudit, db
from time_utils import utc_now


def _hub_descriptions(client, path="/api/tarefas"):
    """Descricoes das tarefas do hub via ``/api/tarefas`` (fonte da SPA).

    Apos o cut-over o hub serve a shell da SPA; a listagem (ativas/arquivadas)
    e consumida do endpoint JSON. Achatamos os grupos em descricoes para validar
    onde cada tarefa aparece.
    """
    payload = client.get(path).get_json()
    assert payload["ok"] is True
    descriptions = []
    for group in payload["data"]["groups"]:
        descriptions.extend(task["descricao"] for task in group["tasks"])
    return descriptions


def _hub_project_ids(client, path="/api/tarefas"):
    """IDs de projeto com grupo (tarefas) na listagem do hub via API."""
    payload = client.get(path).get_json()
    assert payload["ok"] is True
    return {group["project_id"] for group in payload["data"]["groups"]}


def _hub_project_option_values(client, path="/api/tarefas"):
    """Valores das opcoes de projeto (filtro) na listagem do hub via API."""
    payload = client.get(path).get_json()
    assert payload["ok"] is True
    return {opt["value"] for opt in payload["data"]["project_options"]}


def test_finalize_keeps_task_active_and_only_updates_status(
    app, client_user, seed_data
):
    task_id = seed_data["task_id"]

    response = client_user.post(f"/tarefas/{task_id}/finalizar", follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == "finalizada"
        assert task.is_finalized is False
        assert task.finalized_at is None

    assert "Item Auditoria" in _hub_descriptions(client_user)
    assert "Item Auditoria" not in _hub_descriptions(
        client_user, "/api/tarefas?modo=arquivadas"
    )


def test_archive_finalized_moves_task_to_archived_listing(app, client_user, seed_data):
    task_id = seed_data["task_id"]
    client_user.post(f"/tarefas/{task_id}/finalizar", follow_redirects=False)

    response = client_user.post("/tarefas/arquivar-finalizadas", follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == "finalizada"
        assert task.is_finalized is True
        assert task.finalized_at is not None

    assert "Item Auditoria" not in _hub_descriptions(client_user)
    assert "Item Auditoria" in _hub_descriptions(
        client_user, "/api/tarefas?modo=arquivadas"
    )


def test_reactivate_returns_archived_task_to_active_listing_as_programado(
    app, client_user, seed_data
):
    task_id = seed_data["task_id"]
    client_user.post(f"/tarefas/{task_id}/finalizar", follow_redirects=False)
    client_user.post("/tarefas/arquivar-finalizadas", follow_redirects=False)

    response = client_user.post(f"/tarefas/{task_id}/reativar", follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.is_finalized is False
        assert task.finalized_at is None
        assert task.status == "nao_iniciada"

    assert "Item Auditoria" in _hub_descriptions(client_user)
    assert "Item Auditoria" not in _hub_descriptions(
        client_user, "/api/tarefas?modo=arquivadas"
    )


def test_archive_finalized_ajax_returns_archived_ids(app, client_user, seed_data):
    task_id = seed_data["task_id"]
    client_user.post(f"/tarefas/{task_id}/finalizar", follow_redirects=False)

    response = client_user.post(
        "/tarefas/arquivar-finalizadas",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["archived_count"] == 1
    assert payload["archived_task_ids"] == [str(task_id)]


def test_unarchive_ajax_returns_programado_payload(app, client_user, seed_data):
    task_id = seed_data["task_id"]
    client_user.post(f"/tarefas/{task_id}/finalizar", follow_redirects=False)
    client_user.post("/tarefas/arquivar-finalizadas", follow_redirects=False)

    response = client_user.post(
        f"/tarefas/{task_id}/desarquivar",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["task"]["status"] == "nao_iniciada"
    assert payload["item"]["status"] == "nao_iniciada"


def test_archived_alias_redirects_to_archived_route(client_user):
    response = client_user.get(
        "/tarefas/finalizadas?status=finalizado", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/tarefas/arquivadas?status=finalizado"
    )


def test_outsider_cannot_finalize_task(app, client_outsider, seed_data):
    task_id = seed_data["task_id"]

    response = client_outsider.post(
        f"/tarefas/{task_id}/finalizar", follow_redirects=False
    )
    assert response.status_code == 302
    assert "/tarefas" in (response.headers.get("Location") or "")

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.is_finalized is False
        assert task.finalized_at is None
        assert task.status == "nao_iniciada"


def test_collaborator_cannot_move_task_to_finalizada_via_status_update_and_audited(
    app, client_editable, seed_data
):
    task_id = seed_data["task_id"]

    response = client_editable.post(
        f"/tarefas/{task_id}/update_status",
        json={"status": "finalizada"},
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert "Apenas o criador da tarefa" in payload["message"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == "nao_iniciada"

        audit = (
            TaskAccessAudit.query.filter_by(
                task_id=task_id, action_type="forbidden_finalize"
            )
            .order_by(TaskAccessAudit.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_user_id == seed_data["editable_user_id"]
        assert audit.task_author_user_id == seed_data["user_id"]
        assert audit.attempted_status == "finalizada"


def test_collaborator_cannot_finalize_task_via_direct_route_and_audited(
    app, client_editable, seed_data
):
    task_id = seed_data["task_id"]

    response = client_editable.post(
        f"/tarefas/{task_id}/finalizar", follow_redirects=False
    )

    assert response.status_code == 302
    assert "/tarefas" in (response.headers.get("Location") or "")

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == "nao_iniciada"

        audit = (
            TaskAccessAudit.query.filter_by(
                task_id=task_id, action_type="forbidden_finalize"
            )
            .order_by(TaskAccessAudit.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_user_id == seed_data["editable_user_id"]


def test_collaborator_cannot_edit_restricted_fields_via_edit_route_and_audited(
    app, client_editable, seed_data
):
    task_id = seed_data["task_id"]

    response = client_editable.post(
        f"/tarefas/{task_id}/edit",
        data={
            "descricao": "Descricao bloqueada para colaborador",
            "status": "nao_iniciada",
            "responsavel": "Usuario Editavel",
            "prioridade": "alta",
            "tipo_pedido": "",
        },
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert "Somente o autor da tarefa" in payload["message"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.descricao == "Item Auditoria"
        assert task.responsavel == "Usuario Auditoria"
        assert task.prioridade is None

        audit = (
            TaskAccessAudit.query.filter_by(
                task_id=task_id, action_type="forbidden_edit_restricted"
            )
            .order_by(TaskAccessAudit.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_user_id == seed_data["editable_user_id"]
        assert audit.task_author_user_id == seed_data["user_id"]


def test_collaborator_can_still_edit_non_restricted_fields_via_edit_route(
    app, client_editable, seed_data
):
    task_id = seed_data["task_id"]

    response = client_editable.post(
        f"/tarefas/{task_id}/edit",
        data={
            "descricao": "Item Auditoria",
            "status": "em_andamento",
            "responsavel": "Usuario Auditoria",
            "prioridade": "",
            "tipo_pedido": "bug",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["item"]["status"] == "em_andamento"
    assert payload["item"]["tipo_pedido"] == "bug"
    assert payload["item"]["descricao"] == "Item Auditoria"
    assert payload["item"]["responsavel"] == "Usuario Auditoria"
    assert payload["item"]["prioridade"] == ""

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == "em_andamento"
        assert task.tipo_pedido == "bug"
        assert task.descricao == "Item Auditoria"
        assert task.responsavel == "Usuario Auditoria"
        assert task.prioridade is None


def test_collaborator_cannot_update_prioridade_direct_route_and_audited(
    app, client_editable, seed_data
):
    task_id = seed_data["task_id"]

    response = client_editable.post(
        f"/tarefas/{task_id}/update_prioridade",
        json={"prioridade": "alta"},
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert "Somente o autor da tarefa" in payload["message"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.prioridade is None

        audit = (
            TaskAccessAudit.query.filter_by(
                task_id=task_id, action_type="forbidden_edit_restricted"
            )
            .order_by(TaskAccessAudit.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_user_id == seed_data["editable_user_id"]
        assert audit.task_author_user_id == seed_data["user_id"]


def test_admin_can_edit_restricted_fields(app, client_admin, seed_data):
    task_id = seed_data["task_id"]

    response = client_admin.post(
        f"/tarefas/{task_id}/edit",
        data={
            "descricao": "Descricao atualizada por admin",
            "status": "nao_iniciada",
            "responsavel": "Administrador",
            "prioridade": "urgente",
            "tipo_pedido": "",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["item"]["descricao"] == "Descricao atualizada por admin"
    assert payload["item"]["responsavel"] == "Administrador"
    assert payload["item"]["prioridade"] == "urgente"

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.descricao == "Descricao atualizada por admin"
        assert task.responsavel == "Administrador"
        assert task.prioridade == "urgente"


def test_tasks_hub_hides_projects_without_items_until_first_item_is_created(
    app, client_user, seed_data
):
    with app.app_context():
        archived_task = Task(
            descricao="Tarefa arquivada para esconder projeto",
            status="finalizada",
            is_archived=True,
            archived_at=utc_now(),
            project_id=seed_data["project_complete_id"],
            created_by_id=seed_data["user_id"],
        )
        db.session.add(archived_task)
        db.session.commit()

    complete_id = seed_data["project_complete_id"]

    # Sem tarefa ativa o projeto nao tem grupo, mas continua disponivel no
    # filtro de projetos.
    assert complete_id not in _hub_project_ids(client_user)
    assert str(complete_id) in _hub_project_option_values(client_user)

    with app.app_context():
        db.session.add(
            Task(
                descricao="Primeira tarefa ativa do projeto completo",
                status="nao_iniciada",
                project_id=complete_id,
                created_by_id=seed_data["user_id"],
            )
        )
        db.session.commit()

    # Com a primeira tarefa ativa o projeto passa a ter grupo na listagem.
    assert complete_id in _hub_project_ids(client_user)


def test_tasks_hub_serves_spa_shell_for_user_and_admin(client, seed_data):
    # O seletor de orgao migrou para a SPA; aqui garantimos apenas que ambos os
    # papeis recebem a shell da SPA no path nativo.
    with client.session_transaction() as session:
        session["user_id"] = seed_data["user_id"]
        session["login_at"] = time.time()
    user_response = client.get("/tarefas")
    assert user_response.status_code == 200
    assert "data-sveltekit-preload-data" in user_response.get_data(as_text=True)

    with client.session_transaction() as session:
        session["user_id"] = seed_data["admin_id"]
        session["login_at"] = time.time()
    admin_response = client.get("/tarefas")
    assert admin_response.status_code == 200
    assert "data-sveltekit-preload-data" in admin_response.get_data(as_text=True)


def test_finalized_task_is_hidden_from_project_tasks_and_dashboard(
    app, client_user, seed_data
):
    task_id = seed_data["task_id"]
    project_id = seed_data["project_id"]

    client_user.post(f"/tarefas/{task_id}/finalizar", follow_redirects=False)
    client_user.post("/tarefas/arquivar-finalizadas", follow_redirects=False)

    # A listagem do projeto (via API, project filter) nao traz a tarefa arquivada.
    project_descriptions = _hub_descriptions(
        client_user, f"/api/tarefas?project={project_id}"
    )
    assert "Item Auditoria" not in project_descriptions

    # /projeto/<id>/tarefas e um redirect resolver 302 -> /tarefas?project=<id>
    # (a SPA nao tem rota client-side nesse path; o filtro e lido do query param).
    project_tasks_page = client_user.get(
        f"/projeto/{project_id}/tarefas", follow_redirects=False
    )
    assert project_tasks_page.status_code == 302
    assert f"project={project_id}" in project_tasks_page.headers["Location"]


def test_archived_tasks_listing_returns_all_visible_archived_tasks(
    app, client_user, seed_data
):
    # A paginacao virou responsabilidade da SPA; o endpoint JSON do hub devolve
    # todas as tarefas arquivadas visiveis (mesma fonte build_task_hub_context).
    with app.app_context():
        archived_tasks = [
            Task(
                descricao=f"Arquivada paginada {index:02d}",
                status="finalizada",
                ordem=100 + index,
                project_id=seed_data["project_id"],
                created_by_id=seed_data["user_id"],
                is_archived=True,
                archived_at=utc_now(),
            )
            for index in range(25)
        ]
        db.session.add_all(archived_tasks)
        db.session.commit()

    descriptions = _hub_descriptions(client_user, "/api/tarefas?modo=arquivadas")
    for index in range(25):
        assert f"Arquivada paginada {index:02d}" in descriptions


def test_project_tasks_redirects_to_hub_with_project_param(client_user, seed_data):
    # A SPA nao tem rota client-side /projeto/<id>/tarefas: o endpoint preservado
    # redireciona 302 para /tarefas?project=<id> (preservando query params como
    # focus_task); a pagina /tarefas le esses params no mount.
    project_id = seed_data["project_id"]
    response = client_user.get(
        f"/projeto/{project_id}/tarefas?focus_task=7", follow_redirects=False
    )
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/tarefas" in location
    assert f"project={project_id}" in location
    assert "focus_task=7" in location

    # O destino do redirect serve a shell da SPA.
    final_response = client_user.get(location)
    assert final_response.status_code == 200
    assert "data-sveltekit-preload-data" in final_response.get_data(as_text=True)


def test_project_tasks_empty_project_still_redirects_to_hub(client_user, seed_data):
    project_id = seed_data["project_complete_id"]
    response = client_user.get(f"/projeto/{project_id}/tarefas", follow_redirects=False)
    assert response.status_code == 302
    assert f"project={project_id}" in response.headers["Location"]
