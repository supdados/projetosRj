from models import TaskAccessAudit, TaskItem, db

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


def test_delete_task_item_ajax_returns_json_and_deletes_item(
    app, client_user, seed_data
):
    item_id = seed_data["task_item_id"]

    response = client_user.post(f"/tarefas/{item_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["item_id"] == item_id

    with app.app_context():
        assert db.session.get(TaskItem, item_id) is None


def test_delete_task_item_ajax_forbidden_for_outsider(app, client_outsider, seed_data):
    item_id = seed_data["task_item_id"]

    response = client_outsider.post(f"/tarefas/{item_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["item_id"] == item_id

    with app.app_context():
        assert db.session.get(TaskItem, item_id) is not None


def test_delete_task_item_ajax_forbidden_for_non_author_collaborator_and_audited(
    app, client_editable, seed_data
):
    item_id = seed_data["task_item_id"]

    response = client_editable.post(f"/tarefas/{item_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["item_id"] == item_id
    assert "Somente o autor da tarefa" in payload["message"]

    with app.app_context():
        assert db.session.get(TaskItem, item_id) is not None
        audit = (
            TaskAccessAudit.query.filter_by(
                task_id=item_id, action_type="forbidden_delete"
            )
            .order_by(TaskAccessAudit.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_user_id == seed_data["editable_user_id"]
        assert audit.task_author_user_id == seed_data["user_id"]
        assert audit.reason == "not_task_author"


def test_delete_task_item_ajax_error_keeps_json_contract(
    app, client_user, seed_data, monkeypatch
):
    item_id = seed_data["task_item_id"]

    def fail_commit():
        raise Exception("erro-forcado-delete-item")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    response = client_user.post(f"/tarefas/{item_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["item_id"] == item_id
    assert "erro-forcado-delete-item" in payload["message"]

    with app.app_context():
        assert db.session.get(TaskItem, item_id) is not None
