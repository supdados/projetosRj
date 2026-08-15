"""Regras do campo ``tipo_pedido`` nas rotas /api/* (o legado "implementacao" saiu de VALID_TIPOS)."""

from models import Task, TaskItem, db


def test_update_tipo_rejects_implementacao_and_preserves_current_value(
    app, client_user, seed_data
):
    item_id = seed_data["task_item_id"]

    with app.app_context():
        item = db.session.get(TaskItem, item_id)
        assert item is not None
        item.tipo_pedido = "bug"
        db.session.commit()

    response = client_user.post(
        f"/api/tarefas/{item_id}/campos",
        json={"tipo_pedido": "implementacao"},
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation"
    assert payload["error"]["message"] == "Tipo inválido."

    with app.app_context():
        refreshed = db.session.get(TaskItem, item_id)
        assert refreshed is not None
        assert refreshed.tipo_pedido == "bug"


def test_add_task_item_with_implementacao_type_is_sanitized_to_empty(
    app, client_user, seed_data
):
    response = client_user.post(
        "/api/tarefas",
        json={
            "project": str(seed_data["project_id"]),
            "descricao": "Novo item sem tipo legado",
            "status": "nao_iniciada",
            "responsavel": "Usuario Auditoria",
            "prioridade": "",
            "tipo_pedido": "implementacao",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True, payload
    task_payload = payload["data"]["task"]
    assert task_payload["tipo_pedido"] is None

    with app.app_context():
        created = db.session.get(Task, task_payload["id"])
        assert created is not None
        assert created.tipo_pedido is None
