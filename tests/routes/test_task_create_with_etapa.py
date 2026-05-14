"""Garante que POST /tarefas/add aceita etapa_id e valida pertencimento ao projeto."""

from models import Task, db


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


def test_create_task_etapa_from_other_project_returns_400(app, client_user, seed_data):
    project_id = seed_data["project_id"]
    foreign_etapa_id = seed_data["foreign_etapa_id"]

    response = client_user.post(
        "/tarefas/add",
        data={
            "project": str(project_id),
            "etapa": str(foreign_etapa_id),
            "descricao": "Tentativa cross-project",
        },
        headers=_ajax_headers(),
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "projeto" in payload["message"].lower()
