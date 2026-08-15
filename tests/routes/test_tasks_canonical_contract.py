from models import Task, TaskComment, db

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


def _data(response):
    payload = response.get_json()
    assert payload["ok"] is True, payload
    return payload["data"]


def test_add_task_api_creates_task_with_all_fields(app, client_user, seed_data):
    response = client_user.post(
        "/api/tarefas",
        json={
            "titulo": "Tarefa Canonica Nova",
            "project_id": seed_data["project_id"],
            "status": "em_andamento",
            "responsavel": "Usuario Auditoria",
            "prioridade": "alta",
            "tipo_pedido": "bug",
        },
    )

    assert response.status_code == 200
    task_card = _data(response)["task"]
    assert task_card["descricao"] == "Tarefa Canonica Nova"

    with app.app_context():
        task = Task.query.filter_by(descricao="Tarefa Canonica Nova").first()
        assert task is not None
        assert task.project_id == seed_data["project_id"]
        assert task.status == "em_andamento"
        assert task.responsavel == "Usuario Auditoria"
        assert task.prioridade == "alta"
        assert task.tipo_pedido == "bug"


def test_edit_task_api_returns_updated_payload(app, client_user, seed_data):
    task_id = seed_data["task_id"]

    # Campos inline e status vivem em endpoints separados na API (status não é
    # editável por /campos).
    campos_response = client_user.post(
        f"/api/tarefas/{task_id}/campos",
        json={
            "descricao": "Item Auditoria Editado Canonico",
            "responsavel": "Usuario Auditoria",
            "prioridade": "urgente",
            "tipo_pedido": "melhoria",
        },
    )

    assert campos_response.status_code == 200
    campos_data = _data(campos_response)
    assert campos_data["task"]["id"] == task_id
    assert campos_data["task"]["descricao"] == "Item Auditoria Editado Canonico"
    assert campos_data["task"]["prioridade"] == "urgente"
    assert campos_data["task"]["tipo_pedido"] == "melhoria"
    assert campos_data["detail"]["permissions"]["can_delete"] is True
    assert campos_data["detail"]["permissions"]["can_finalize"] is True

    status_response = client_user.post(
        f"/api/tarefas/{task_id}/status",
        json={"status": "para_validacao"},
    )
    assert status_response.status_code == 200
    assert _data(status_response)["task"]["status"] == "para_validacao"

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.descricao == "Item Auditoria Editado Canonico"
        assert task.status == "para_validacao"
        assert task.prioridade == "urgente"
        assert task.tipo_pedido == "melhoria"


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
        f"/api/tarefas/{seed_data['task_id']}/sugestoes-responsavel",
        query_string={"q": "Usuario"},
    )

    assert task_response.status_code == 200
    task_names = [user["name"] for user in _data(task_response)["users"]]
    assert "Usuario Auditoria" in task_names
    assert "Usuario VPD" not in task_names

    hub_response = client_user.get(
        "/api/tarefas/sugestoes-responsavel",
        query_string={"orgao": str(seed_data["auditoria_orgao_id"]), "q": "Admin"},
    )

    assert hub_response.status_code == 200
    hub_names = [user["name"] for user in _data(hub_response)["users"]]
    assert hub_names == ["Administrador"]


def test_task_assignable_users_rejects_cross_orgao_lookup(client_user, seed_data):
    response = client_user.get(
        "/api/tarefas/sugestoes-responsavel",
        query_string={"orgao": str(seed_data["vpd_orgao_id"])},
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "forbidden"
    assert "Sem permissão" in payload["error"]["message"]
