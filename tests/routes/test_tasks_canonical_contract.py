from models import Task, TaskComment, db

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


def test_add_task_canonical_creates_task_and_redirects_to_project_board(
    app, client_user, seed_data
):
    response = client_user.post(
        "/tarefas/add",
        data={
            "titulo": "Tarefa Canonica Nova",
            "project_id": str(seed_data["project_id"]),
            "status": "em_andamento",
            "responsavel": "Usuario Auditoria",
            "prioridade": "alta",
            "tipo_pedido": "bug",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert f"/projeto/{seed_data['project_id']}/tarefas" in response.headers["Location"]

    with app.app_context():
        task = Task.query.filter_by(descricao="Tarefa Canonica Nova").first()
        assert task is not None
        assert task.project_id == seed_data["project_id"]
        assert task.status == "em_andamento"
        assert task.responsavel == "Usuario Auditoria"
        assert task.prioridade == "alta"
        assert task.tipo_pedido == "bug"


def test_edit_task_canonical_returns_updated_payload(app, client_user, seed_data):
    response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/edit",
        data={
            "descricao": "Item Auditoria Editado Canonico",
            "status": "para_validacao",
            "responsavel": "Usuario Auditoria",
            "prioridade": "urgente",
            "tipo_pedido": "melhoria",
            "project_id": str(seed_data["project_id"]),
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task"]["descricao"] == "Item Auditoria Editado Canonico"
    assert payload["task"]["status"] == "para_validacao"
    assert payload["task"]["prioridade"] == "urgente"
    assert payload["task"]["tipo_pedido"] == "melhoria"
    assert payload["task"]["can_delete"] is True
    assert payload["task"]["can_finalize"] is True
    assert payload["item"]["id"] == seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, seed_data["task_id"])
        assert task is not None
        assert task.descricao == "Item Auditoria Editado Canonico"
        assert task.status == "para_validacao"


def test_delete_task_canonical_ajax_removes_task(app, client_user, seed_data):
    response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/delete",
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["item_id"] == seed_data["task_id"]

    with app.app_context():
        assert db.session.get(Task, seed_data["task_id"]) is None


def test_update_task_status_and_prioridade_canonical_json(app, client_user, seed_data):
    status_response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/update_status",
        json={"status": "em_andamento"},
    )
    assert status_response.status_code == 200
    assert status_response.get_json()["success"] is True

    prioridade_response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/update_prioridade",
        json={"prioridade": "alta"},
    )
    assert prioridade_response.status_code == 200
    prioridade_payload = prioridade_response.get_json()
    assert prioridade_payload["success"] is True
    assert prioridade_payload["prioridade"] == "alta"

    with app.app_context():
        task = db.session.get(Task, seed_data["task_id"])
        assert task is not None
        assert task.status == "em_andamento"
        assert task.prioridade == "alta"


def test_add_and_edit_task_comment_on_canonical_routes(app, client_user, seed_data):
    add_response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/comentarios/add",
        headers=AJAX_HEADERS,
        data={"content": "Comentario canonico novo"},
    )

    assert add_response.status_code == 200
    add_payload = add_response.get_json()
    assert add_payload["success"] is True
    assert add_payload["comment"]["content"] == "Comentario canonico novo"
    assert add_payload["comment"]["author_name"] == "Usuario Auditoria"

    comment_id = add_payload["comment"]["id"]

    edit_response = client_user.post(
        f"/tarefas/comentarios/{comment_id}/edit",
        headers=AJAX_HEADERS,
        data={"content": "Comentario canonico editado"},
    )

    assert edit_response.status_code == 200
    edit_payload = edit_response.get_json()
    assert edit_payload["success"] is True
    assert edit_payload["comment"]["content"] == "Comentario canonico editado"
    assert edit_payload["comment"]["updated_at"] is not None

    with app.app_context():
        comment = db.session.get(TaskComment, comment_id)
        assert comment is not None
        assert comment.content == "Comentario canonico editado"


def test_task_assignable_users_routes_return_orgao_scoped_names(client_user, seed_data):
    task_response = client_user.get(
        f"/tarefas/{seed_data['task_id']}/sugestoes-responsavel",
        query_string={"q": "Usuario"},
    )

    assert task_response.status_code == 200
    task_payload = task_response.get_json()
    task_names = [user["name"] for user in task_payload["users"]]
    assert "Usuario Auditoria" in task_names
    assert "Usuario VPD" not in task_names

    hub_response = client_user.get(
        "/tarefas/sugestoes-responsavel",
        query_string={"orgao": str(seed_data["auditoria_orgao_id"]), "q": "Admin"},
    )

    assert hub_response.status_code == 200
    hub_payload = hub_response.get_json()
    hub_names = [user["name"] for user in hub_payload["users"]]
    assert hub_names == ["Administrador"]
