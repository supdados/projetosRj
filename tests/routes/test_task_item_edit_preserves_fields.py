from models import TaskItem, db


def test_edit_task_item_preserves_prioridade_and_tipo_when_fields_are_omitted(app, client_user, seed_data):
    item_id = seed_data['task_item_id']

    with app.app_context():
        item = db.session.get(TaskItem, item_id)
        assert item is not None
        item.prioridade = 'alta'
        item.tipo_pedido = 'bug'
        db.session.commit()
        descricao = item.descricao
        status = item.status

    response = client_user.post(
        f'/tarefas/itens/{item_id}/edit',
        data={
            'descricao': descricao,
            'status': status,
            'responsavel': 'Usuario Auditoria',
        },
        headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['item']['prioridade'] == 'alta'
    assert payload['item']['tipo_pedido'] == 'bug'

    with app.app_context():
        refreshed = db.session.get(TaskItem, item_id)
        assert refreshed is not None
        assert refreshed.prioridade == 'alta'
        assert refreshed.tipo_pedido == 'bug'
