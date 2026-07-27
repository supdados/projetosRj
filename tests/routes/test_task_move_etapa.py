"""Cobre a rota POST /tarefas/<id>/mover-etapa usada pelo DnD do hub."""

from models import Etapa, Task, db
from routes.api.envelope import NOT_FOUND_MESSAGE


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


def test_move_task_to_other_project_etapa_is_indistinguishable_from_missing(
    app, client_user, seed_data
):
    """S5/F4-2b: etapa alheia e etapa inexistente colapsam no MESMO 404.

    Substitui o contrato pré-S5 (400 "não pertence ao projeto"), que confirmava
    a existência do id ao atacante. A tarefa não muda de etapa nos dois casos.
    """
    task_id = seed_data["task_id"]

    def _move(etapa_id):
        return client_user.post(
            f"/tarefas/{task_id}/mover-etapa",
            json={"etapa_id": etapa_id},
            headers=_ajax_headers(),
        )

    foreign = _move(seed_data["foreign_etapa_id"])
    missing = _move(999999)

    assert foreign.status_code == 404
    assert foreign.get_json()["success"] is False
    assert foreign.get_json()["message"] == NOT_FOUND_MESSAGE
    assert foreign.status_code == missing.status_code
    assert foreign.get_data() == missing.get_data()

    with app.app_context():
        assert db.session.get(Task, task_id).etapa_id is None


def test_move_task_to_done_etapa_succeeds_with_warning(app, client_user, seed_data):
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

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["etapa_id"] == done_etapa_id
    assert "concluída" in payload["warning"].lower()


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
