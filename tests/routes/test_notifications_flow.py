from models import Etapa, Project, TaskItem, TaskItemComment, User, UserArea, UserNotification, db


def _create_user(username, name, *, areas=None, is_admin=False):
    user = User(
        username=username,
        name=name,
        orgao='Orgao Teste',
        is_admin=is_admin,
    )
    user.set_password('senha123')
    db.session.add(user)
    db.session.flush()

    for area in areas or []:
        db.session.add(UserArea(user_id=user.id, area=area))

    return user


def _client_for_user(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = user_id
    return client


def test_notifications_dropdown_marks_as_read(app, client_user, seed_data):
    with app.app_context():
        actor = _create_user('notif_actor_1', 'Notif Actor 1', areas=['Auditoria'])
        actor_id = actor.id
        db.session.commit()

    actor_client = _client_for_user(app, actor_id)
    response = actor_client.post(
        f"/tarefas/itens/{seed_data['task_item_id']}/update_status",
        json={'status': 'validacao'},
    )
    assert response.status_code == 200

    with app.app_context():
        unread = UserNotification.query.filter_by(
            recipient_user_id=seed_data['user_id'],
            is_read=False,
        ).count()
        assert unread > 0

    dropdown_response = client_user.post('/api/notificacoes/dropdown')
    assert dropdown_response.status_code == 200
    payload = dropdown_response.get_json()
    assert payload['unread_before'] > 0
    assert payload['unread_after'] == 0
    assert isinstance(payload['items'], list)
    assert payload['items']

    with app.app_context():
        unread_after = UserNotification.query.filter_by(
            recipient_user_id=seed_data['user_id'],
            is_read=False,
        ).count()
        assert unread_after == 0


def test_comment_reply_notifies_previous_participant(app, client_user, seed_data):
    with app.app_context():
        user_b = _create_user('notif_user_b', 'Notif User B', areas=['Auditoria'])
        user_b_id = user_b.id
        db.session.commit()

    client_b = _client_for_user(app, user_b_id)

    first_comment_response = client_b.post(
        f"/tarefas/itens/{seed_data['task_item_id']}/comentarios/add",
        headers={'X-Requested-With': 'XMLHttpRequest'},
        data={'content': 'Comentario do usuario B'},
    )
    assert first_comment_response.status_code == 200

    second_comment_response = client_user.post(
        f"/tarefas/itens/{seed_data['task_item_id']}/comentarios/add",
        headers={'X-Requested-With': 'XMLHttpRequest'},
        data={'content': 'Resposta do usuario A'},
    )
    assert second_comment_response.status_code == 200

    with app.app_context():
        notification_for_b = (
            UserNotification.query
            .filter_by(recipient_user_id=user_b_id, event_type='task_item_comment_added')
            .order_by(UserNotification.id.desc())
            .first()
        )
        assert notification_for_b is not None
        assert 'Resposta do usuario A' in notification_for_b.message


def test_status_change_by_other_user_notifies_task_creator(app, seed_data):
    with app.app_context():
        actor = _create_user('notif_actor_2', 'Notif Actor 2', areas=['Auditoria'])
        actor_id = actor.id
        db.session.commit()

    actor_client = _client_for_user(app, actor_id)
    response = actor_client.post(
        f"/tarefas/itens/{seed_data['task_item_id']}/update_status",
        json={'status': 'em_andamento'},
    )
    assert response.status_code == 200

    with app.app_context():
        notification = (
            UserNotification.query
            .filter_by(
                recipient_user_id=seed_data['user_id'],
                event_type='task_item_status_updated',
            )
            .order_by(UserNotification.id.desc())
            .first()
        )
        assert notification is not None
        assert 'alterou o status' in notification.message


def test_assignment_change_notifies_assigned_user(app, seed_data):
    with app.app_context():
        actor = _create_user('notif_actor_3', 'Notif Actor 3', areas=['Auditoria'])
        assignee = _create_user('notif_assignee_1', 'Notif Assignee 1', areas=['Auditoria'])
        actor_id = actor.id
        assignee_id = assignee.id
        db.session.commit()

        item = db.session.get(TaskItem, seed_data['task_item_id'])
        assert item is not None
        current_status = item.status
        current_description = item.descricao

    actor_client = _client_for_user(app, actor_id)
    response = actor_client.post(
        f"/tarefas/itens/{seed_data['task_item_id']}/edit",
        data={
            'descricao': current_description,
            'status': current_status,
            'responsavel': 'Notif Assignee 1',
            'prioridade': '',
            'tipo_pedido': '',
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    with app.app_context():
        notification = (
            UserNotification.query
            .filter_by(recipient_user_id=assignee_id, event_type='task_item_assignment')
            .order_by(UserNotification.id.desc())
            .first()
        )
        assert notification is not None
        assert 'mudou de' in notification.message


def test_project_stage_change_notifies_project_owner(app, client_user, seed_data):
    with app.app_context():
        actor = _create_user('notif_actor_4', 'Notif Actor 4', areas=['Auditoria'])
        actor_id = actor.id
        db.session.commit()

    actor_client = _client_for_user(app, actor_id)
    response = actor_client.post(
        f"/etapa/{seed_data['etapa_id']}/update_field",
        json={'field': 'descricao', 'value': 'Etapa alterada para notificar'},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    with app.app_context():
        notification = (
            UserNotification.query
            .filter(
                UserNotification.recipient_user_id == seed_data['user_id'],
                UserNotification.event_type == 'project_edit_etapa_inline',
            )
            .order_by(UserNotification.id.desc())
            .first()
        )
        assert notification is not None
        assert 'Alterou' in notification.message


def test_legacy_project_without_owner_notifies_area_admin(app):
    with app.app_context():
        area_admin = _create_user('area_admin_1', 'Area Admin 1', areas=['CHEGAB'], is_admin=True)
        actor = _create_user('legacy_actor_1', 'Legacy Actor 1', areas=['CHEGAB'])

        legacy_project = Project(
            titulo='Projeto Legado Sem Dono',
            area_responsavel='CHEGAB',
            orgao='Orgao Legado',
            prioridade='media',
            status='Vigente',
            observacao='Projeto sem historico de dono',
        )
        db.session.add(legacy_project)
        db.session.flush()

        legacy_stage = Etapa(
            descricao='Etapa Legada',
            project_id=legacy_project.id,
            ordem=0,
            iniciada=False,
            done=False,
        )
        db.session.add(legacy_stage)
        db.session.commit()

        actor_id = actor.id
        area_admin_id = area_admin.id
        legacy_stage_id = legacy_stage.id

    actor_client = _client_for_user(app, actor_id)
    response = actor_client.post(
        f'/etapa/{legacy_stage_id}/toggle_iniciada',
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    with app.app_context():
        notification = (
            UserNotification.query
            .filter(
                UserNotification.recipient_user_id == area_admin_id,
                UserNotification.event_type == 'project_toggle_iniciada',
            )
            .order_by(UserNotification.id.desc())
            .first()
        )
        assert notification is not None
