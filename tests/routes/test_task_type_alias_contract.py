from models import Task, db


def _data(response):
    payload = response.get_json()
    assert payload["ok"] is True, payload
    return payload["data"]


def test_update_task_tipo_api_updates_value_and_returns_payload(
    app, client_user, seed_data
):
    task_id = seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        task.tipo_pedido = "bug"
        db.session.commit()

    response = client_user.post(
        f"/api/tarefas/{task_id}/campos",
        json={"tipo_pedido": "melhoria"},
    )

    assert response.status_code == 200
    assert _data(response)["task"]["tipo_pedido"] == "melhoria"

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.tipo_pedido == "melhoria"


def test_update_task_tipo_api_allows_clearing_value(app, client_user, seed_data):
    task_id = seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        task.tipo_pedido = "duvida"
        db.session.commit()

    response = client_user.post(
        f"/api/tarefas/{task_id}/campos",
        json={"tipo_pedido": ""},
    )

    assert response.status_code == 200
    assert _data(response)["task"]["tipo_pedido"] is None

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.tipo_pedido is None


def test_update_task_prioridade_api_uses_same_contract(app, client_user, seed_data):
    item_id = seed_data["task_item_id"]

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        item.prioridade = "baixa"
        db.session.commit()

    response = client_user.post(
        f"/api/tarefas/{item_id}/campos",
        json={"prioridade": "alta"},
    )

    assert response.status_code == 200
    assert _data(response)["task"]["prioridade"] == "alta"

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        assert item.prioridade == "alta"


def test_update_task_tipo_api_sets_outros_value(app, client_user, seed_data):
    item_id = seed_data["task_item_id"]

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        item.tipo_pedido = "bug"
        db.session.commit()

    response = client_user.post(
        f"/api/tarefas/{item_id}/campos",
        json={"tipo_pedido": "outros"},
    )

    assert response.status_code == 200
    assert _data(response)["task"]["tipo_pedido"] == "outros"

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        assert item.tipo_pedido == "outros"
