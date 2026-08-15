from models import TaskItem, db

# Os testes de reorder por ESCOPO (projeto/orfa) do hub Jinja foram removidos
# junto com POST /tarefas/reordenar: a SPA persiste ordem por COLUNA via
# POST /api/tarefas/board/reordenar (contrato em test_api_board_contract.py) e a
# semantica pura de apply_task_order segue coberta em test_task_mutation_unit.py.


def test_reorder_tasks_board_persists_order_after_status_change(
    app, client_user, seed_data
):
    with app.app_context():
        anchor = db.session.get(TaskItem, seed_data["task_id"])
        assert anchor is not None

        top_item = TaskItem(
            descricao="Hub topo validacao",
            status="para_validacao",
            responsavel="Usuario Auditoria",
            ordem=2,
            project_id=anchor.project_id,
            created_by_id=anchor.created_by_id,
        )
        moved_item = TaskItem(
            descricao="Hub mover para validacao",
            status="em_andamento",
            responsavel="Usuario Auditoria",
            ordem=3,
            project_id=anchor.project_id,
            created_by_id=anchor.created_by_id,
        )
        bottom_item = TaskItem(
            descricao="Hub base validacao",
            status="para_validacao",
            responsavel="Usuario Auditoria",
            ordem=4,
            project_id=anchor.project_id,
            created_by_id=anchor.created_by_id,
        )
        db.session.add_all([top_item, moved_item, bottom_item])
        db.session.commit()

        top_item_id = top_item.id
        moved_item_id = moved_item.id
        bottom_item_id = bottom_item.id

    status_response = client_user.post(
        f"/api/tarefas/{moved_item_id}/status",
        json={"status": "para_validacao"},
    )
    assert status_response.status_code == 200

    reorder_response = client_user.post(
        "/api/tarefas/board/reordenar",
        json={
            "columns": [
                {
                    "status": "para_validacao",
                    "task_ids": [top_item_id, moved_item_id, bottom_item_id],
                }
            ]
        },
    )

    assert reorder_response.status_code == 200
    reorder_payload = reorder_response.get_json()
    assert reorder_payload["ok"] is True
    column = reorder_payload["data"]["columns"][0]
    assert [card["id"] for card in column["tasks"]] == [
        top_item_id,
        moved_item_id,
        bottom_item_id,
    ]

    with app.app_context():
        assert db.session.get(TaskItem, moved_item_id).status == "para_validacao"
        assert db.session.get(TaskItem, top_item_id).ordem == 1
        assert db.session.get(TaskItem, moved_item_id).ordem == 2
        assert db.session.get(TaskItem, bottom_item_id).ordem == 3

    # O hub agora serve a SPA; a ordem visivel vem de /api/tarefas (mesma fonte
    # build_task_hub_context, ordenada por ordem/id).
    payload = client_user.get("/api/tarefas").get_json()
    assert payload["ok"] is True
    descriptions = []
    for group in payload["data"]["groups"]:
        descriptions.extend(task["descricao"] for task in group["tasks"])
    assert (
        descriptions.index("Hub topo validacao")
        < descriptions.index("Hub mover para validacao")
        < descriptions.index("Hub base validacao")
    )
