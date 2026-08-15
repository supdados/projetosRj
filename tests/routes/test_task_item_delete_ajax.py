import logging

from models import TaskAccessAudit, TaskItem, db


def test_delete_task_item_api_returns_envelope_and_deletes_item(
    app, client_user, seed_data
):
    item_id = seed_data["task_item_id"]

    response = client_user.post(f"/api/tarefas/{item_id}/excluir")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["item_id"] == item_id

    with app.app_context():
        assert db.session.get(TaskItem, item_id) is None


def test_delete_task_item_api_forbidden_for_non_author_collaborator_and_audited(
    app, client_editable, seed_data
):
    item_id = seed_data["task_item_id"]

    response = client_editable.post(f"/api/tarefas/{item_id}/excluir")

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "forbidden"
    assert "Somente o autor da tarefa" in payload["error"]["message"]

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


def test_delete_task_item_api_error_keeps_json_contract(
    app, client_user, seed_data, monkeypatch, caplog
):
    """500 mantém o envelope JSON; o detalhe da exceção só vai para o log.

    A mensagem crua não é ecoada ao cliente (``fail_internal``, OWASP A09/A10) —
    nada de detalhe interno no corpo, e o traceback preservado no log do servidor.
    """
    item_id = seed_data["task_item_id"]

    def fail_commit():
        raise Exception("erro-forcado-delete-item")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    with caplog.at_level(logging.ERROR):
        response = client_user.post(f"/api/tarefas/{item_id}/excluir")

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "server"
    assert "erro-forcado-delete-item" not in response.get_data(as_text=True)
    assert "erro-forcado-delete-item" in caplog.text

    with app.app_context():
        assert db.session.get(TaskItem, item_id) is not None
