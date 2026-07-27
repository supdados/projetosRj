import logging

from models import TaskAccessAudit, TaskItem, db
from routes.tasks.crud import GENERIC_DB_ERROR_MESSAGE

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


def test_delete_task_item_ajax_not_found_for_outsider(app, client_outsider, seed_data):
    """S5/F4-2: rank 0 vira 404; ``item_id`` continua ecoando o id PEDIDO."""
    item_id = seed_data["task_item_id"]

    response = client_outsider.post(f"/tarefas/{item_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 404
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
    app, client_user, seed_data, monkeypatch, caplog
):
    """500 mantém o envelope JSON; o detalhe da exceção só vai para o log.

    A mensagem crua deixou de ser ecoada ao cliente (``GENERIC_DB_ERROR_MESSAGE``,
    OWASP A09/A10) — o teste passou a exigir o oposto: nada de detalhe interno no
    corpo, e o traceback preservado no log do servidor.
    """
    item_id = seed_data["task_item_id"]

    def fail_commit():
        raise Exception("erro-forcado-delete-item")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    with caplog.at_level(logging.ERROR):
        response = client_user.post(f"/tarefas/{item_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["item_id"] == item_id
    assert payload["message"] == GENERIC_DB_ERROR_MESSAGE
    assert "erro-forcado-delete-item" not in response.get_data(as_text=True)
    assert "erro-forcado-delete-item" in caplog.text

    with app.app_context():
        assert db.session.get(TaskItem, item_id) is not None
