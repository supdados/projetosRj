from models import TaskItem, db

# Os 2 testes legacy de reorder de itens (POST /tarefas/<id>/itens/reordenar)
# foram removidos junto com a rota orfa: a semantica de reorder por escopo de
# projeto/orfa ja e coberta pelos testes test_reorder_tasks_hub_* abaixo
# (via /tarefas/reordenar, mesmo servico apply_task_order + dedup/filtragem).


def test_reorder_tasks_hub_persists_order_after_status_change(
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
        foreign_before = db.session.get(TaskItem, seed_data["foreign_task_id"]).ordem

    status_response = client_user.post(
        f"/tarefas/{moved_item_id}/update_status",
        json={"status": "para_validacao"},
    )
    assert status_response.status_code == 200

    reorder_response = client_user.post(
        "/tarefas/reordenar",
        json={
            "ordem": [
                seed_data["task_id"],
                top_item_id,
                moved_item_id,
                bottom_item_id,
                seed_data["foreign_task_id"],
            ]
        },
    )

    assert reorder_response.status_code == 200
    payload = reorder_response.get_json()
    assert payload["success"] is True

    with app.app_context():
        anchor = db.session.get(TaskItem, seed_data["task_id"])
        assert anchor is not None

        ordered_items = (
            TaskItem.query.filter(
                TaskItem.project_id == anchor.project_id,
                TaskItem.is_archived.is_(False),
            )
            .order_by(TaskItem.ordem.asc(), TaskItem.id.asc())
            .all()
        )
        ordered_ids = [item.id for item in ordered_items]
        assert ordered_ids == [
            seed_data["task_id"],
            top_item_id,
            moved_item_id,
            bottom_item_id,
        ]
        assert db.session.get(TaskItem, moved_item_id).status == "para_validacao"
        assert (
            db.session.get(TaskItem, seed_data["foreign_task_id"]).ordem
            == foreign_before
        )

    page_response = client_user.get("/tarefas")
    assert page_response.status_code == 200
    html = page_response.get_data(as_text=True)
    assert (
        html.index("Hub topo validacao")
        < html.index("Hub mover para validacao")
        < html.index("Hub base validacao")
    )


def test_reorder_tasks_hub_applies_mixed_payload_per_scope(app, client_user, seed_data):
    with app.app_context():
        first_project_extra = TaskItem(
            descricao="Hub projeto principal extra",
            status="em_andamento",
            responsavel="Usuario Auditoria",
            ordem=2,
            project_id=seed_data["project_id"],
            created_by_id=seed_data["user_id"],
        )
        second_project_first = TaskItem(
            descricao="Hub projeto secundario 1",
            status="nao_iniciada",
            responsavel="Usuario Auditoria",
            ordem=1,
            project_id=seed_data["project_complete_id"],
            created_by_id=seed_data["user_id"],
        )
        second_project_second = TaskItem(
            descricao="Hub projeto secundario 2",
            status="para_validacao",
            responsavel="Usuario Auditoria",
            ordem=2,
            project_id=seed_data["project_complete_id"],
            created_by_id=seed_data["user_id"],
        )
        orphan_extra = TaskItem(
            descricao="Hub orfa extra",
            status="finalizada",
            responsavel="Usuario Auditoria",
            ordem=2,
            project_id=None,
            created_by_id=seed_data["user_id"],
        )
        foreign_orphan = TaskItem(
            descricao="Hub orfa estrangeira",
            status="nao_iniciada",
            responsavel="Usuario VPD",
            ordem=1,
            project_id=None,
            created_by_id=seed_data["outsider_id"],
        )
        db.session.add_all(
            [
                first_project_extra,
                second_project_first,
                second_project_second,
                orphan_extra,
                foreign_orphan,
            ]
        )
        db.session.commit()

        first_project_extra_id = first_project_extra.id
        second_project_first_id = second_project_first.id
        second_project_second_id = second_project_second.id
        orphan_extra_id = orphan_extra.id
        foreign_orphan_id = foreign_orphan.id
        foreign_project_before = db.session.get(
            TaskItem, seed_data["foreign_task_id"]
        ).ordem
        foreign_orphan_before = db.session.get(TaskItem, foreign_orphan_id).ordem

    response = client_user.post(
        "/tarefas/reordenar",
        json={
            "ordem": [
                second_project_second_id,
                orphan_extra_id,
                first_project_extra_id,
                seed_data["foreign_task_id"],
                seed_data["orphan_task_id"],
                second_project_first_id,
                seed_data["task_id"],
                foreign_orphan_id,
            ]
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True

    with app.app_context():
        first_project_ids = [
            item.id
            for item in (
                TaskItem.query.filter(
                    TaskItem.project_id == seed_data["project_id"],
                    TaskItem.is_archived.is_(False),
                )
                .order_by(TaskItem.ordem.asc(), TaskItem.id.asc())
                .all()
            )
        ]
        second_project_ids = [
            item.id
            for item in (
                TaskItem.query.filter(
                    TaskItem.project_id == seed_data["project_complete_id"],
                    TaskItem.is_archived.is_(False),
                )
                .order_by(TaskItem.ordem.asc(), TaskItem.id.asc())
                .all()
            )
        ]
        own_orphan_ids = [
            item.id
            for item in (
                TaskItem.query.filter(
                    TaskItem.project_id.is_(None),
                    TaskItem.created_by_id == seed_data["user_id"],
                    TaskItem.is_archived.is_(False),
                )
                .order_by(TaskItem.ordem.asc(), TaskItem.id.asc())
                .all()
            )
        ]

        assert first_project_ids == [first_project_extra_id, seed_data["task_id"]]
        assert second_project_ids == [second_project_second_id, second_project_first_id]
        assert own_orphan_ids == [orphan_extra_id, seed_data["orphan_task_id"]]
        assert (
            db.session.get(TaskItem, seed_data["foreign_task_id"]).ordem
            == foreign_project_before
        )
        assert (
            db.session.get(TaskItem, foreign_orphan_id).ordem == foreign_orphan_before
        )


def test_reorder_tasks_hub_admin_reorders_all_orphans_in_single_scope(
    app, client_admin, seed_data
):
    with app.app_context():
        admin_orphan_user = TaskItem(
            descricao="Hub orfa admin usuario",
            status="em_andamento",
            responsavel="Usuario Auditoria",
            ordem=2,
            project_id=None,
            created_by_id=seed_data["user_id"],
        )
        admin_orphan_outsider = TaskItem(
            descricao="Hub orfa admin outsider",
            status="para_validacao",
            responsavel="Usuario VPD",
            ordem=3,
            project_id=None,
            created_by_id=seed_data["outsider_id"],
        )
        db.session.add_all([admin_orphan_user, admin_orphan_outsider])
        db.session.commit()

        admin_orphan_user_id = admin_orphan_user.id
        admin_orphan_outsider_id = admin_orphan_outsider.id
        project_before = db.session.get(TaskItem, seed_data["task_id"]).ordem

    response = client_admin.post(
        "/tarefas/reordenar",
        json={
            "ordem": [
                admin_orphan_outsider_id,
                seed_data["orphan_task_id"],
                admin_orphan_user_id,
            ]
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True

    with app.app_context():
        orphan_ids = [
            item.id
            for item in (
                TaskItem.query.filter(
                    TaskItem.project_id.is_(None),
                    TaskItem.is_archived.is_(False),
                )
                .order_by(TaskItem.ordem.asc(), TaskItem.id.asc())
                .all()
            )
        ]

        assert orphan_ids == [
            admin_orphan_outsider_id,
            seed_data["orphan_task_id"],
            admin_orphan_user_id,
        ]
        assert db.session.get(TaskItem, seed_data["task_id"]).ordem == project_before
