"""Garante que POST /api/tarefas aceita etapa e valida pertencimento ao projeto."""

from models import Task, db
from routes.api.envelope import NOT_FOUND_MESSAGE


def _ok(response):
    payload = response.get_json()
    assert payload["ok"] is True, payload
    return payload["data"]


def test_create_task_with_valid_etapa_persists_etapa_id(app, client_user, seed_data):
    project_id = seed_data["project_id"]
    etapa_id = seed_data["etapa_id"]

    response = client_user.post(
        "/api/tarefas",
        json={
            "project": str(project_id),
            "etapa": str(etapa_id),
            "descricao": "Nova com etapa",
        },
    )

    assert response.status_code == 200
    task_payload = _ok(response)["task"]
    assert task_payload["etapa_id"] == etapa_id

    with app.app_context():
        task = db.session.get(Task, task_payload["id"])
        assert task.etapa_id == etapa_id
        assert task.project_id == project_id


def test_create_task_without_etapa_keeps_field_null(app, client_user, seed_data):
    project_id = seed_data["project_id"]

    response = client_user.post(
        "/api/tarefas",
        json={
            "project": str(project_id),
            "descricao": "Sem etapa",
        },
    )

    assert response.status_code == 200
    task_payload = _ok(response)["task"]
    assert task_payload["etapa_id"] is None

    with app.app_context():
        task = db.session.get(Task, task_payload["id"])
        assert task.etapa_id is None


def test_create_task_etapa_from_other_project_is_indistinguishable_from_missing(
    app, client_user, seed_data
):
    """S5/F4-2b: etapa alheia e etapa inexistente colapsam no MESMO 404.

    Substitui o contrato pré-S5 (400 "não pertence ao projeto"), que confirmava
    a existência do id ao atacante. A tarefa segue não criada nos dois casos.
    """
    project_id = seed_data["project_id"]

    def _post(etapa_value):
        return client_user.post(
            "/api/tarefas",
            json={
                "project": str(project_id),
                "etapa": str(etapa_value),
                "descricao": "Tentativa cross-project",
            },
        )

    foreign = _post(seed_data["foreign_etapa_id"])
    missing = _post(999999)

    assert foreign.status_code == 404
    payload = foreign.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["message"] == NOT_FOUND_MESSAGE
    assert foreign.status_code == missing.status_code
    assert payload == missing.get_json()

    with app.app_context():
        assert Task.query.filter_by(descricao="Tentativa cross-project").first() is None
