"""Garante que uma etapa com tarefas abertas não pode ser concluída."""

from models import Etapa, Task, db


def _ajax_headers():
    return {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}


def _make_etapa_with_open_task(app, seed_data, *, task_status="em_andamento"):
    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        task = Task(
            descricao="Tarefa aberta",
            status=task_status,
            project_id=etapa.project_id,
            etapa_id=etapa.id,
            created_by_id=seed_data["user_id"],
            ordem=1,
        )
        db.session.add(task)
        db.session.commit()
        return etapa.id, task.id


def test_toggle_etapa_blocked_when_open_task_exists(app, client_admin, seed_data):
    etapa_id, _ = _make_etapa_with_open_task(app, seed_data)

    response = client_admin.post(f"/etapa/{etapa_id}/toggle", headers=_ajax_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["done"] is False
    assert payload["open_task_count"] == 1
    assert "pendente" in payload["message"].lower()

    with app.app_context():
        assert db.session.get(Etapa, etapa_id).done is False


def test_toggle_etapa_succeeds_when_all_tasks_finalizadas(app, client_admin, seed_data):
    etapa_id, task_id = _make_etapa_with_open_task(
        app, seed_data, task_status="finalizada"
    )

    response = client_admin.post(f"/etapa/{etapa_id}/toggle", headers=_ajax_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["done"] is True


def test_toggle_etapa_ignores_archived_tasks(app, client_admin, seed_data):
    etapa_id, task_id = _make_etapa_with_open_task(app, seed_data)

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.is_archived = True
        db.session.commit()

    response = client_admin.post(f"/etapa/{etapa_id}/toggle", headers=_ajax_headers())
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["done"] is True


def test_unmarking_done_is_not_blocked_by_open_tasks(app, client_admin, seed_data):
    etapa_id, _ = _make_etapa_with_open_task(app, seed_data)

    with app.app_context():
        # Forçamos a etapa para done=True direto no banco (cenário de dado legado).
        etapa = db.session.get(Etapa, etapa_id)
        etapa.done = True
        db.session.commit()

    response = client_admin.post(f"/etapa/{etapa_id}/toggle", headers=_ajax_headers())
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["done"] is False
