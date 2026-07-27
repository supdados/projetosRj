from models import TaskItem, db

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


def test_task_hub_global_add_item_in_filtered_project(app, client_user, seed_data):
    response = client_user.post(
        "/tarefas/add",
        headers=AJAX_HEADERS,
        data={
            "project": str(seed_data["project_id"]),
            "descricao": "Item global no projeto filtrado",
            "status": "nao_iniciada",
            "responsavel": "Usuario Auditoria",
            "prioridade": "media",
            "tipo_pedido": "bug",
        },
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["success"] is True
    assert payload["item"]["project_id"] == seed_data["project_id"]
    assert payload["item"]["task_id"] == payload["item"]["id"]
    assert payload["item"]["project_titulo"] == "Projeto Auditoria"
    assert payload["item"]["can_delete"] is True
    assert payload["item"]["can_finalize"] is True

    with app.app_context():
        item = db.session.get(TaskItem, payload["item"]["id"])
        assert item is not None
        assert item.project_id == seed_data["project_id"]


def test_task_hub_global_add_item_without_filter_choosing_project(
    client_user, seed_data
):
    response = client_user.post(
        "/tarefas/add",
        headers=AJAX_HEADERS,
        data={
            "project": str(seed_data["project_id"]),
            "descricao": "Item kanban sem filtro escolhendo projeto",
            "status": "em_andamento",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["item"]["project_id"] == seed_data["project_id"]


def test_task_hub_global_add_item_in_sem_projeto_anchor(client_user, seed_data):
    response = client_user.post(
        "/tarefas/add",
        headers=AJAX_HEADERS,
        data={
            "project": "sem_projeto",
            "descricao": "Item sem projeto criado no hub",
            "status": "nao_iniciada",
        },
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["success"] is True
    assert payload["item"]["project_id"] is None
    assert payload["item"]["task_id"] == payload["item"]["id"]
    assert payload["item"]["project_value"] == "sem_projeto"


def test_task_hub_global_add_not_found_for_outsider(client_outsider, seed_data):
    """S5/F4-2: projeto invisível responde o mesmo 404 do projeto inexistente."""
    response = client_outsider.post(
        "/tarefas/add",
        headers=AJAX_HEADERS,
        data={
            "project": str(seed_data["project_id"]),
            "descricao": "Tentativa sem permissao",
        },
    )
    inexistente = client_outsider.post(
        "/tarefas/add",
        headers=AJAX_HEADERS,
        data={"project": "999999", "descricao": "Tentativa sem permissao"},
    )

    assert response.status_code == 404
    assert response.get_json()["success"] is False
    assert response.get_json() == inexistente.get_json()


def test_task_hub_assignable_users_by_project_context(client_user, seed_data):
    response = client_user.get(
        "/tarefas/sugestoes-responsavel",
        query_string={"project": str(seed_data["project_id"]), "q": "Usuario"},
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert isinstance(payload.get("users"), list)
    names = [user.get("name") for user in payload["users"]]
    assert "Usuario Auditoria" in names
