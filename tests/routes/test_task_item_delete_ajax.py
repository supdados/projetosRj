from models import TaskItem, db


AJAX_HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json',
}


def test_delete_task_item_ajax_returns_json_and_deletes_item(app, client_user, seed_data):
    item_id = seed_data['task_item_id']

    response = client_user.post(f'/tarefas/itens/{item_id}/delete', headers=AJAX_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['item_id'] == item_id

    with app.app_context():
        assert TaskItem.query.get(item_id) is None


def test_delete_task_item_ajax_forbidden_for_outsider(app, client_outsider, seed_data):
    item_id = seed_data['task_item_id']

    response = client_outsider.post(f'/tarefas/itens/{item_id}/delete', headers=AJAX_HEADERS)

    assert response.status_code == 403
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['item_id'] == item_id

    with app.app_context():
        assert TaskItem.query.get(item_id) is not None


def test_delete_task_item_ajax_error_keeps_json_contract(app, client_user, seed_data, monkeypatch):
    item_id = seed_data['task_item_id']

    def fail_commit():
        raise Exception('erro-forcado-delete-item')

    monkeypatch.setattr(db.session, 'commit', fail_commit)

    response = client_user.post(f'/tarefas/itens/{item_id}/delete', headers=AJAX_HEADERS)

    assert response.status_code == 500
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['item_id'] == item_id
    assert 'erro-forcado-delete-item' in payload['message']

    with app.app_context():
        assert TaskItem.query.get(item_id) is not None
