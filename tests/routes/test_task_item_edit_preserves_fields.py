from models import TaskItem, db


def test_edit_task_item_preserves_prioridade_and_tipo_when_fields_are_omitted(
    app, client_user, seed_data
):
    item_id = seed_data["task_item_id"]

    with app.app_context():
        item = db.session.get(TaskItem, item_id)
        assert item is not None
        item.prioridade = "alta"
        item.tipo_pedido = "bug"
        db.session.commit()
        descricao = item.descricao

    response = client_user.post(
        f"/api/tarefas/{item_id}/campos",
        json={
            "descricao": descricao,
            "responsavel": "Usuario Auditoria",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True, payload
    task_payload = payload["data"]["task"]
    assert task_payload["prioridade"] == "alta"
    assert task_payload["tipo_pedido"] == "bug"

    with app.app_context():
        refreshed = db.session.get(TaskItem, item_id)
        assert refreshed is not None
        assert refreshed.prioridade == "alta"
        assert refreshed.tipo_pedido == "bug"
