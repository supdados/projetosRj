from models import TaskItem, db


def _data(response):
    payload = response.get_json()
    assert payload["ok"] is True, payload
    return payload["data"]


def test_task_hub_global_add_item_in_filtered_project(app, client_user, seed_data):
    response = client_user.post(
        "/api/tarefas",
        json={
            "project": str(seed_data["project_id"]),
            "descricao": "Item global no projeto filtrado",
            "status": "nao_iniciada",
            "responsavel": "Usuario Auditoria",
            "prioridade": "media",
            "tipo_pedido": "bug",
        },
    )
    assert response.status_code == 200

    task = _data(response)["task"]
    assert task["project_id"] == seed_data["project_id"]
    assert task["project_titulo"] == "Projeto Auditoria"
    assert task["permissions"]["can_delete"] is True
    assert task["permissions"]["can_finalize"] is True

    with app.app_context():
        item = db.session.get(TaskItem, task["id"])
        assert item is not None
        assert item.project_id == seed_data["project_id"]


def test_task_hub_global_add_item_in_sem_projeto_anchor(app, client_user, seed_data):
    response = client_user.post(
        "/api/tarefas",
        json={
            "project": "sem_projeto",
            "descricao": "Item sem projeto criado no hub",
            "status": "nao_iniciada",
        },
    )
    assert response.status_code == 200

    task = _data(response)["task"]
    assert task["project_id"] is None
    assert task["project_titulo"] == "Sem projeto"

    with app.app_context():
        item = db.session.get(TaskItem, task["id"])
        assert item is not None
        assert item.project_id is None


def test_task_hub_global_add_not_found_for_outsider(client_outsider, seed_data):
    """S5/F4-2: projeto invisível responde o mesmo 404 do projeto inexistente."""
    response = client_outsider.post(
        "/api/tarefas",
        json={
            "project": str(seed_data["project_id"]),
            "descricao": "Tentativa sem permissao",
        },
    )
    inexistente = client_outsider.post(
        "/api/tarefas",
        json={"project": "999999", "descricao": "Tentativa sem permissao"},
    )

    assert response.status_code == 404
    assert response.get_json()["ok"] is False
    assert response.get_json() == inexistente.get_json()
