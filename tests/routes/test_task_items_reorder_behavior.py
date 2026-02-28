from models import TaskItem, db


def test_reorder_task_items_applies_order_for_task_items_only(app, client_user, seed_data):
    with app.app_context():
        task_id = seed_data['task_id']
        first_item_id = seed_data['task_item_id']
        anchor = db.session.get(TaskItem, task_id)
        assert anchor is not None

        second_item = TaskItem(
            descricao='Item adicional 2',
            status='programado',
            responsavel='Usuario Auditoria',
            ordem=2,
            project_id=anchor.project_id,
            created_by_id=anchor.created_by_id,
        )
        third_item = TaskItem(
            descricao='Item adicional 3',
            status='validacao',
            responsavel='Usuario Auditoria',
            ordem=3,
            project_id=anchor.project_id,
            created_by_id=anchor.created_by_id,
        )
        db.session.add_all([second_item, third_item])
        db.session.commit()
        second_item_id = second_item.id
        third_item_id = third_item.id

    response = client_user.post(
        f'/tarefas/{seed_data["task_id"]}/itens/reordenar',
        json={'ordem': [third_item_id, first_item_id, second_item_id]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    with app.app_context():
        anchor = db.session.get(TaskItem, seed_data['task_id'])
        assert anchor is not None
        ordered_ids = [
            item.id
            for item in (
                TaskItem.query
                .filter(
                    TaskItem.project_id == anchor.project_id,
                    TaskItem.is_archived.is_(False),
                )
                .order_by(TaskItem.ordem.asc())
                .all()
            )
        ]
        assert ordered_ids == [third_item_id, first_item_id, second_item_id]


def test_reorder_task_items_ignores_duplicates_invalid_and_foreign_ids(app, client_user, seed_data):
    with app.app_context():
        task_id = seed_data['task_id']
        first_item_id = seed_data['task_item_id']
        foreign_item_id = seed_data['foreign_task_item_id']
        anchor = db.session.get(TaskItem, task_id)
        assert anchor is not None

        second_item = TaskItem(
            descricao='Item adicional 2',
            status='programado',
            responsavel='Usuario Auditoria',
            ordem=2,
            project_id=anchor.project_id,
            created_by_id=anchor.created_by_id,
        )
        third_item = TaskItem(
            descricao='Item adicional 3',
            status='finalizado',
            responsavel='Usuario Auditoria',
            ordem=3,
            project_id=anchor.project_id,
            created_by_id=anchor.created_by_id,
        )
        db.session.add_all([second_item, third_item])
        db.session.commit()
        second_item_id = second_item.id
        third_item_id = third_item.id

        foreign_before = db.session.get(TaskItem, foreign_item_id).ordem

    response = client_user.post(
        f'/tarefas/{task_id}/itens/reordenar',
        json={
            'ordem': [
                foreign_item_id,
                third_item_id,
                'abc',
                third_item_id,
                second_item_id,
            ]
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    with app.app_context():
        anchor = db.session.get(TaskItem, task_id)
        assert anchor is not None
        ordered_items = (
            TaskItem.query
            .filter(
                TaskItem.project_id == anchor.project_id,
                TaskItem.is_archived.is_(False),
            )
            .order_by(TaskItem.ordem.asc())
            .all()
        )
        ordered_ids = [item.id for item in ordered_items]
        ordered_ordens = [item.ordem for item in ordered_items]

        assert ordered_ids == [third_item_id, second_item_id, first_item_id]
        assert ordered_ordens == [1, 2, 3]
        assert db.session.get(TaskItem, foreign_item_id).ordem == foreign_before
