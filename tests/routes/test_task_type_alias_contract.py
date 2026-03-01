from models import Task, db


def test_update_task_tipo_canonical_updates_value_and_returns_payload(app, client_user, seed_data):
    task_id = seed_data['task_id']

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        task.tipo_pedido = 'bug'
        db.session.commit()

    response = client_user.post(
        f'/tarefas/{task_id}/update_tipo',
        json={'tipo_pedido': 'melhoria'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {'success': True, 'tipo_pedido': 'melhoria'}

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.tipo_pedido == 'melhoria'


def test_update_task_tipo_canonical_allows_clearing_value(app, client_user, seed_data):
    task_id = seed_data['task_id']

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        task.tipo_pedido = 'duvida'
        db.session.commit()

    response = client_user.post(
        f'/tarefas/{task_id}/update_tipo',
        json={'tipo_pedido': ''},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {'success': True, 'tipo_pedido': ''}

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.tipo_pedido is None


def test_update_task_item_prioridade_alias_uses_same_contract(app, client_user, seed_data):
    item_id = seed_data['task_item_id']

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        item.prioridade = 'baixa'
        db.session.commit()

    response = client_user.post(
        f'/tarefas/itens/{item_id}/update_prioridade',
        json={'prioridade': 'alta'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {'success': True, 'prioridade': 'alta'}

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        assert item.prioridade == 'alta'


def test_update_task_item_tipo_alias_uses_same_contract(app, client_user, seed_data):
    item_id = seed_data['task_item_id']

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        item.tipo_pedido = 'bug'
        db.session.commit()

    response = client_user.post(
        f'/tarefas/itens/{item_id}/update_tipo',
        json={'tipo_pedido': 'outros'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {'success': True, 'tipo_pedido': 'outros'}

    with app.app_context():
        item = db.session.get(Task, item_id)
        assert item is not None
        assert item.tipo_pedido == 'outros'
