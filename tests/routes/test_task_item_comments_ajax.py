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


def test_delete_task_item_comment_ajax_not_found_for_outsider(
    app, client_outsider, seed_data
):
    """S5/F4-2b: quem não vê a tarefa nem descobre que o comentário existe."""
    comment_id = seed_data["comment_id"]
    headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}

    response = client_outsider.post(
        f"/tarefas/comentarios/{comment_id}/delete", headers=headers
    )
    inexistente = client_outsider.post(
        "/tarefas/comentarios/999999/delete", headers=headers
    )

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert payload == inexistente.get_json()

    with app.app_context():
        assert db.session.get(TaskItemComment, comment_id) is not None
