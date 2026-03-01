from models import TaskItem, db


def test_update_tipo_rejects_implementacao_and_preserves_current_value(app, client_user, seed_data):
    item_id = seed_data['task_item_id']

    with app.app_context():
        item = db.session.get(TaskItem, item_id)
        assert item is not None
        item.tipo_pedido = 'bug'
        db.session.commit()

    response = client_user.post(
        f'/tarefas/itens/{item_id}/update_tipo',
        json={'tipo_pedido': 'implementacao'},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['message'] == 'Tipo inválido'

    with app.app_context():
        refreshed = db.session.get(TaskItem, item_id)
        assert refreshed is not None
        assert refreshed.tipo_pedido == 'bug'


def test_edit_task_item_preserves_legacy_implementacao_when_submitted(app, client_user, seed_data):
    item_id = seed_data['task_item_id']

    with app.app_context():
        item = db.session.get(TaskItem, item_id)
        assert item is not None
        item.tipo_pedido = 'implementacao'
        db.session.commit()
        descricao = item.descricao
        status = item.status

    response = client_user.post(
        f'/tarefas/itens/{item_id}/edit',
        data={
            'descricao': descricao,
            'status': status,
            'responsavel': 'Usuario Auditoria',
            'prioridade': '',
            'tipo_pedido': 'implementacao',
        },
        headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['item']['tipo_pedido'] == 'implementacao'

    with app.app_context():
        refreshed = db.session.get(TaskItem, item_id)
        assert refreshed is not None
        assert refreshed.tipo_pedido == 'implementacao'


def test_add_task_item_with_implementacao_type_is_sanitized_to_empty(app, client_user, seed_data):
    response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/itens/add",
        data={
            'descricao': 'Novo item sem tipo legado',
            'status': 'nao_iniciada',
            'responsavel': 'Usuario Auditoria',
            'prioridade': '',
            'tipo_pedido': 'implementacao',
        },
        headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['item']['tipo_pedido'] == ''

    with app.app_context():
        created_item = db.session.get(TaskItem, payload['item']['id'])
        assert created_item is not None
        assert created_item.tipo_pedido is None
