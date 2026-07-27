"""Garante que POST /tarefas/add aceita etapa_id e valida pertencimento ao projeto."""

from models import Task, db
from routes.api.envelope import NOT_FOUND_MESSAGE


def _ajax_headers():
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def test_create_task_with_valid_etapa_persists_etapa_id(app, client_user, seed_data):
    project_id = seed_data["project_id"]
    etapa_id = seed_data["etapa_id"]

    response = client_user.post(
        "/tarefas/add",
        data={
            "project": str(project_id),
            "etapa": str(etapa_id),
            "descricao": "Nova com etapa",
        },
        headers=_ajax_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    new_task_id = payload["task"]["id"]
    assert payload["task"]["etapa_id"] == etapa_id

    with app.app_context():
        task = db.session.get(Task, new_task_id)
        assert task.etapa_id == etapa_id
        assert task.project_id == project_id


def test_create_task_without_etapa_keeps_field_null(app, client_user, seed_data):
    project_id = seed_data["project_id"]

    response = client_user.post(
        "/tarefas/add",
        data={
            "project": str(project_id),
            "descricao": "Legado sem etapa",
        },
        headers=_ajax_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    new_task_id = payload["task"]["id"]
    assert payload["task"]["etapa_id"] is None

    with app.app_context():
        task = db.session.get(Task, new_task_id)
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
            "/tarefas/add",
            data={
                "project": str(project_id),
                "etapa": str(etapa_value),
                "descricao": "Tentativa cross-project",
            },
            headers=_ajax_headers(),
        )

    foreign = _post(seed_data["foreign_etapa_id"])
    missing = _post(999999)

    assert foreign.status_code == 404
    assert foreign.get_json()["success"] is False
    assert foreign.get_json()["message"] == NOT_FOUND_MESSAGE
    assert foreign.status_code == missing.status_code
    assert foreign.get_data() == missing.get_data()

    with app.app_context():
        assert Task.query.filter_by(descricao="Tentativa cross-project").first() is None
