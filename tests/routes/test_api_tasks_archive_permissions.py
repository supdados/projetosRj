"""Regressão dos bugs 2.5/2.6 (auditoria docs/auditoria-logica-2026-07-17.md):

    - 2.5: ``/api/tarefas/<id>/desarquivar`` só checava ``_can_view_task``,
      deixando qualquer usuário do escopo do órgão desarquivar tarefa alheia.
      Agora usa o MESMO guard restrito de arquivar/deletar/finalizar
      (``_can_manage_task_restricted_actions``).
    - 2.6: ``/api/tarefas/arquivar-finalizadas`` arquivava TODAS as tarefas
      finalizadas visíveis no escopo dos filtros, mesmo as de outro autor.
      Agora filtra para autor/admin antes de arquivar; as demais ficam intactas.

Reusa as fixtures de ``tests/conftest.py`` (``client_user``, ``client_admin``,
``client_editable``, ``seed_data``).
"""

from __future__ import annotations

from models import Task, TaskAccessAudit, db


def test_desarquivar_nao_autor_nao_admin_toma_403(app, client_editable, seed_data):
    task_id = seed_data["task_id"]
    user_id = seed_data["user_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.status = "finalizada"
        task.is_archived = True
        db.session.commit()

    response = client_editable.post(f"/api/tarefas/{task_id}/desarquivar", json={})

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "forbidden"

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task.is_archived is True

        audit = (
            TaskAccessAudit.query.filter_by(
                task_id=task_id, action_type="forbidden_edit_restricted"
            )
            .order_by(TaskAccessAudit.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor_user_id == seed_data["editable_user_id"]
        assert audit.task_author_user_id == user_id


def test_desarquivar_autor_consegue(app, client_user, seed_data):
    task_id = seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.status = "finalizada"
        task.is_archived = True
        db.session.commit()

    response = client_user.post(f"/api/tarefas/{task_id}/desarquivar", json={})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task.is_archived is False
        assert task.status == "nao_iniciada"


def test_desarquivar_admin_consegue(app, client_admin, seed_data):
    task_id = seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.status = "finalizada"
        task.is_archived = True
        db.session.commit()

    response = client_admin.post(f"/api/tarefas/{task_id}/desarquivar", json={})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True


def test_arquivar_finalizadas_lote_nao_arquiva_tarefa_alheia(
    app, client_editable, seed_data
):
    task_id = seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.status = "finalizada"
        db.session.commit()

    response = client_editable.post("/api/tarefas/arquivar-finalizadas", json={})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    data = payload["data"]
    assert task_id not in [int(tid) for tid in data["archived_task_ids"]]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task.is_archived is False


def test_arquivar_finalizadas_lote_do_autor_arquiva(app, client_user, seed_data):
    task_id = seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.status = "finalizada"
        db.session.commit()

    response = client_user.post("/api/tarefas/arquivar-finalizadas", json={})

    assert response.status_code == 200
    payload = response.get_json()
    data = payload["data"]
    assert str(task_id) in data["archived_task_ids"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task.is_archived is True


def test_arquivar_finalizadas_lote_admin_arquiva_tarefa_alheia(
    app, client_admin, seed_data
):
    task_id = seed_data["task_id"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        task.status = "finalizada"
        db.session.commit()

    response = client_admin.post("/api/tarefas/arquivar-finalizadas", json={})

    assert response.status_code == 200
    payload = response.get_json()
    data = payload["data"]
    assert str(task_id) in data["archived_task_ids"]

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task.is_archived is True
