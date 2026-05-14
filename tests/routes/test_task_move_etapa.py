"""Cobre a rota POST /tarefas/<id>/mover-etapa usada pelo DnD do hub."""

from models import Etapa, Task, db


def _ajax_headers():
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def test_move_task_to_same_project_etapa_succeeds(app, client_user, seed_data):
    task_id = seed_data["task_id"]
    etapa_id = seed_data["etapa_started_id"]

    response = client_user.post(
        f"/tarefas/{task_id}/mover-etapa",
        json={"etapa_id": etapa_id},
        headers=_ajax_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["etapa_id"] == etapa_id

    with app.app_context():
        refreshed = db.session.get(Task, task_id)
        assert refreshed.etapa_id == etapa_id


def test_move_task_to_empty_etapa_clears_field(app, client_user, seed_data):
    task_id = seed_data["task_id"]
    etapa_id = seed_data["etapa_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.etapa_id = etapa_id
        db.session.commit()

    response = client_user.post(
        f"/tarefas/{task_id}/mover-etapa",
        json={"etapa_id": "sem_etapa"},
        headers=_ajax_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["etapa_id"] is None
    assert payload["previous_etapa_id"] == etapa_id


def test_move_task_to_other_project_etapa_returns_400(app, client_user, seed_data):
    task_id = seed_data["task_id"]
    foreign_etapa_id = seed_data["foreign_etapa_id"]

    response = client_user.post(
        f"/tarefas/{task_id}/mover-etapa",
        json={"etapa_id": foreign_etapa_id},
        headers=_ajax_headers(),
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "projeto" in payload["message"].lower()


def test_move_task_to_done_etapa_returns_400(app, client_user, seed_data):
    task_id = seed_data["task_id"]
    project_id = seed_data["project_id"]

    with app.app_context():
        done_etapa = Etapa(
            descricao="Concluida",
            iniciada=True,
            done=True,
            project_id=project_id,
            ordem=99,
        )
        db.session.add(done_etapa)
        db.session.commit()
        done_etapa_id = done_etapa.id

    response = client_user.post(
        f"/tarefas/{task_id}/mover-etapa",
        json={"etapa_id": done_etapa_id},
        headers=_ajax_headers(),
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "concluída" in payload["message"].lower()


def test_move_task_with_invalid_etapa_id_returns_400(app, client_user, seed_data):
    task_id = seed_data["task_id"]

    response = client_user.post(
        f"/tarefas/{task_id}/mover-etapa",
        json={"etapa_id": "nao-numerico"},
        headers=_ajax_headers(),
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False


def test_move_task_unknown_task_returns_404(app, client_user, seed_data):
    response = client_user.post(
        "/tarefas/999999/mover-etapa",
        json={"etapa_id": seed_data["etapa_id"]},
        headers=_ajax_headers(),
    )

    assert response.status_code == 404
