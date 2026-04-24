from models import (
    Project,
    ProjectHistory,
    Task,
    TaskComment,
    User,
    UserNotification,
    db,
)
from services.notifications import (
    _resolve_admin_ids_for_orgao,
    create_user_notifications,
    resolve_project_owner_user_ids,
    resolve_task_collaborator_user_ids,
)
from tests._orgao_helpers import ensure_orgao, link_user_to_orgao


def _create_user(username, name, *, is_admin=False, areas=None):
    user = User(
        username=username,
        name=name,
        orgao="Orgao Teste",
        is_admin=is_admin,
    )
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()

    for area in areas or []:
        link_user_to_orgao(user.id, area)

    return user


def _create_project(title="Projeto Notificacoes", area="Auditoria"):
    orgao = ensure_orgao(area)
    project = Project(
        titulo=title,
        orgao_id=orgao.id,
        orgao="Orgao Teste",
        prioridade="media",
        status="Vigente",
        objetivo_id=1,
        resultado_esperado_id=1,
    )
    db.session.add(project)
    db.session.flush()
    return project


def test_create_user_notifications_deduplicates_discards_actor_and_ignores_unknown_ids(
    app,
):
    with app.app_context():
        actor = _create_user("actor_notif", "Actor Notif")
        recipient_a = _create_user("recipient_a", "Recipient A")
        recipient_b = _create_user("recipient_b", "Recipient B")
        db.session.commit()

        created_count = create_user_notifications(
            [
                recipient_b.id,
                recipient_a.id,
                recipient_a.id,
                str(actor.id),
                999999,
                None,
            ],
            actor_user_id=actor.id,
            event_type="unit_event",
            title="Titulo",
            message="Mensagem",
            target_url="/alvo",
        )
        db.session.commit()

        assert created_count == 2

        notifications = UserNotification.query.order_by(
            UserNotification.recipient_user_id.asc()
        ).all()
        assert [notification.recipient_user_id for notification in notifications] == [
            recipient_a.id,
            recipient_b.id,
        ]
        assert all(
            notification.actor_user_id == actor.id for notification in notifications
        )
        assert all(
            notification.event_type == "unit_event" for notification in notifications
        )
        assert all(notification.target_url == "/alvo" for notification in notifications)


def test_resolve_admin_ids_for_orgao_scopes_when_possible_and_falls_back_to_all_admins(
    app,
):
    with app.app_context():
        auditoria_admin = _create_user(
            "admin_auditoria",
            "Admin Auditoria",
            is_admin=True,
            areas=["Auditoria"],
        )
        vpd_admin = _create_user(
            "admin_vpd",
            "Admin VPD",
            is_admin=True,
            areas=["VPD"],
        )
        _create_user("usuario_comum", "Usuario Comum", areas=["Auditoria"])
        db.session.commit()

        auditoria_id = ensure_orgao("Auditoria").id
        chegab_id = ensure_orgao("CHEGAB").id
        assert _resolve_admin_ids_for_orgao(auditoria_id) == {auditoria_admin.id}
        assert _resolve_admin_ids_for_orgao(chegab_id) == {
            auditoria_admin.id,
            vpd_admin.id,
        }
        assert _resolve_admin_ids_for_orgao(None) == {auditoria_admin.id, vpd_admin.id}


def test_resolve_project_owner_prefers_explicit_create_history_entry(app):
    with app.app_context():
        creator = _create_user("creator_owner", "Creator Owner", areas=["Auditoria"])
        other_user = _create_user("other_owner", "Other Owner", areas=["Auditoria"])
        project = _create_project(title="Projeto Criado", area="Auditoria")
        db.session.add_all(
            [
                ProjectHistory(
                    project_id=project.id,
                    user_id=creator.id,
                    action_type="create",
                    action_description="Criou o projeto",
                ),
                ProjectHistory(
                    project_id=project.id,
                    user_id=other_user.id,
                    action_type="edit",
                    action_description="Editou o projeto",
                ),
            ]
        )
        db.session.commit()

        assert resolve_project_owner_user_ids(project) == {creator.id}


def test_resolve_project_owner_single_non_create_history_falls_back_to_area_admins(app):
    with app.app_context():
        area_admin = _create_user(
            "admin_area_owner",
            "Admin Area Owner",
            is_admin=True,
            areas=["Auditoria"],
        )
        foreign_admin = _create_user(
            "admin_other_area",
            "Admin Other Area",
            is_admin=True,
            areas=["VPD"],
        )
        actor = _create_user("legacy_actor", "Legacy Actor", areas=["Auditoria"])
        project = _create_project(title="Projeto Legado", area="Auditoria")
        db.session.add(
            ProjectHistory(
                project_id=project.id,
                user_id=actor.id,
                action_type="edit",
                action_description="Primeira ação legada",
            )
        )
        db.session.commit()

        assert resolve_project_owner_user_ids(project) == {area_admin.id}
        assert resolve_project_owner_user_ids(project) != {foreign_admin.id}


def test_resolve_project_owner_with_multiple_non_create_entries_keeps_first_actor(app):
    with app.app_context():
        first_actor = _create_user("first_actor", "First Actor", areas=["Auditoria"])
        second_actor = _create_user("second_actor", "Second Actor", areas=["Auditoria"])
        _create_user("admin_actor", "Admin Actor", is_admin=True, areas=["Auditoria"])
        project = _create_project(title="Projeto Historico", area="Auditoria")
        db.session.add_all(
            [
                ProjectHistory(
                    project_id=project.id,
                    user_id=first_actor.id,
                    action_type="edit",
                    action_description="Primeira ação",
                ),
                ProjectHistory(
                    project_id=project.id,
                    user_id=second_actor.id,
                    action_type="add_etapa",
                    action_description="Segunda ação",
                ),
            ]
        )
        db.session.commit()

        assert resolve_project_owner_user_ids(project) == {first_actor.id}


def test_resolve_project_owner_without_history_falls_back_to_area_admins(app):
    with app.app_context():
        area_admin = _create_user(
            "admin_without_history",
            "Admin Without History",
            is_admin=True,
            areas=["Auditoria"],
        )
        _create_user(
            "other_admin_without_history",
            "Other Admin Without History",
            is_admin=True,
            areas=["VPD"],
        )
        project = _create_project(title="Projeto Sem Historico", area="Auditoria")
        db.session.commit()

        assert resolve_project_owner_user_ids(project) == {area_admin.id}


def test_resolve_task_collaborator_user_ids_deduplicates_creator_responsaveis_and_commenters(
    app,
):
    with app.app_context():
        creator = _create_user("task_creator", "Task Creator", areas=["Auditoria"])
        maria = _create_user("maria_silva", "Maria Silva", areas=["Auditoria"])
        joao = _create_user("joao_souza", "Joao Souza", areas=["Auditoria"])
        comment_author = _create_user(
            "comment_author", "Comment Author", areas=["Auditoria"]
        )

        task = Task(
            descricao="Tarefa para colaboradores",
            status="nao_iniciada",
            responsavel=" Maria Silva ; @Joao Souza ; Maria Silva ; Desconhecido ",
            project_id=None,
            created_by_id=creator.id,
        )
        db.session.add(task)
        db.session.flush()

        db.session.add_all(
            [
                TaskComment(
                    content="Comentario do criador", user_id=creator.id, task_id=task.id
                ),
                TaskComment(
                    content="Comentario externo",
                    user_id=comment_author.id,
                    task_id=task.id,
                ),
                TaskComment(
                    content="Comentario externo 2",
                    user_id=comment_author.id,
                    task_id=task.id,
                ),
            ]
        )
        db.session.commit()

        assert resolve_task_collaborator_user_ids(task) == {
            creator.id,
            maria.id,
            joao.id,
            comment_author.id,
        }
