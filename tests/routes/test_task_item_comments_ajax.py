from models import TaskItemComment, db


def test_delete_task_item_comment_ajax_returns_json_and_deletes_comment(
    app, client_user, seed_data
):
    comment_id = seed_data["comment_id"]

    response = client_user.post(
        f"/tarefas/comentarios/{comment_id}/delete",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["comment_id"] == comment_id

    with app.app_context():
        assert db.session.get(TaskItemComment, comment_id) is None


def test_delete_task_item_comment_ajax_forbidden_for_non_owner(
    app, client_outsider, seed_data
):
    comment_id = seed_data["comment_id"]

    response = client_outsider.post(
        f"/tarefas/comentarios/{comment_id}/delete",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["comment_id"] == comment_id

    with app.app_context():
        assert db.session.get(TaskItemComment, comment_id) is not None
