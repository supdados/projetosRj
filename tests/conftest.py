import datetime
import os

import pytest
from sqlalchemy.pool import NullPool

os.environ.setdefault('SKIP_STARTUP_DB_INIT', 'true')

from app import create_app
from models import (
    CalendarEvent,
    Etapa,
    IndicadorProjeto,
    AreaCatalog,
    Project,
    ProjectHistory,
    StageTemplate,
    StageTemplateItem,
    Task,
    TaskItem,
    TaskItemComment,
    User,
    UserArea,
    db,
)
from catalogs.objectives import sync_goal_catalog_to_db
from routes.shared import ensure_area_catalog_seeded

TEST_PASSWORD = 'senha123'


def _create_user(username, name, *, is_admin=False, areas=None, orgao='Orgao Teste'):
    user = User(
        username=username,
        name=name,
        orgao=orgao,
        is_admin=is_admin,
    )
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.flush()

    for area in areas or []:
        db.session.add(UserArea(user_id=user.id, area=area))

    return user


def _login(client, user_id):
    with client.session_transaction() as session:
        session['user_id'] = user_id


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / 'test.sqlite'
    flask_app = create_app(
        {
            'TESTING': True,
            'SECRET_KEY': 'test-secret-key',
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
            'SQLALCHEMY_ENGINE_OPTIONS': {'poolclass': NullPool},
            'SKIP_STARTUP_DB_INIT': True,
            'WTF_CSRF_ENABLED': False,
        }
    )

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        ensure_area_catalog_seeded()
        sync_goal_catalog_to_db(commit=True)

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_data(app):
    with app.app_context():
        admin = _create_user('admin', 'Administrador', is_admin=True, areas=['Auditoria'])
        user = _create_user('user_auditoria', 'Usuario Auditoria', areas=['Auditoria'])
        outsider = _create_user('user_vpd', 'Usuario VPD', areas=['VPD'])
        editable = _create_user('user_editavel', 'Usuario Editavel', areas=['Auditoria'])
        deletable = _create_user('user_deletavel', 'Usuario Deletavel', areas=['SUPDADOS'])

        template = StageTemplate(name='Template Base', description='Template inicial de teste')
        db.session.add(template)
        db.session.flush()
        db.session.add_all(
            [
                StageTemplateItem(name='Planejamento', duration_days=2, order=0, templateId=template.id),
                StageTemplateItem(name='Execucao', duration_days=3, order=1, templateId=template.id),
            ]
        )

        project = Project(
            titulo='Projeto Auditoria',
            area_responsavel='Auditoria',
            orgao='Orgao A',
            prioridade='alta',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
            observacao='Projeto principal para testes',
        )
        db.session.add(project)
        db.session.flush()
        db.session.add(IndicadorProjeto(project_id=project.id, indicador_id=1))

        etapa = Etapa(
            descricao='Etapa Planejada',
            data_inicio=datetime.date(2026, 1, 10),
            data_fim=datetime.date(2026, 1, 15),
            responsavel='Usuario Auditoria',
            iniciada=False,
            done=False,
            comentarios='Sem comentarios',
            project_id=project.id,
            ordem=0,
        )
        etapa_started = Etapa(
            descricao='Etapa Iniciada',
            data_inicio=datetime.date(2026, 1, 16),
            data_fim=datetime.date(2026, 1, 20),
            responsavel='Usuario Auditoria',
            iniciada=True,
            done=False,
            comentarios='Em andamento',
            project_id=project.id,
            ordem=1,
        )
        db.session.add_all([etapa, etapa_started])

        project_complete = Project(
            titulo='Projeto Concluivel',
            area_responsavel='Auditoria',
            orgao='Orgao A',
            prioridade='media',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
            observacao='Projeto pronto para concluir',
        )
        db.session.add(project_complete)
        db.session.flush()
        db.session.add(
            Etapa(
                descricao='Etapa Finalizada',
                data_inicio=datetime.date(2026, 2, 1),
                data_fim=datetime.date(2026, 2, 3),
                responsavel='Usuario Auditoria',
                iniciada=True,
                done=True,
                comentarios='Concluida',
                project_id=project_complete.id,
                ordem=0,
            )
        )

        foreign_project = Project(
            titulo='Projeto VPD',
            area_responsavel='VPD',
            orgao='Orgao B',
            prioridade='baixa',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
            observacao='Projeto para teste de permissao',
        )
        db.session.add(foreign_project)
        db.session.flush()
        foreign_etapa = Etapa(
            descricao='Etapa VPD',
            data_inicio=datetime.date(2026, 1, 5),
            data_fim=datetime.date(2026, 1, 12),
            responsavel='Usuario VPD',
            iniciada=True,
            done=False,
            comentarios='Etapa area VPD',
            project_id=foreign_project.id,
            ordem=0,
        )
        db.session.add(foreign_etapa)

        task = Task(
            descricao='Item Auditoria',
            status='nao_iniciada',
            responsavel='Usuario Auditoria',
            ordem=1,
            project_id=project.id,
            created_by_id=user.id,
        )
        foreign_task = Task(
            descricao='Item VPD',
            status='em_andamento',
            responsavel='Usuario VPD',
            ordem=1,
            project_id=foreign_project.id,
            created_by_id=outsider.id,
        )
        orphan_task = Task(
            descricao='Tarefa Sem Projeto',
            status='nao_iniciada',
            ordem=1,
            project_id=None,
            created_by_id=user.id,
        )
        db.session.add_all([task, foreign_task, orphan_task])
        db.session.flush()

        calendar_event = CalendarEvent(
            user_id=user.id,
            title='Evento Seed',
            description='Evento inicial de calendário para testes',
            location='Sala 101',
            starts_at=datetime.datetime(2026, 3, 10, 12, 0),
            ends_at=datetime.datetime(2026, 3, 10, 13, 0),
            source='app',
            sync_status='pending',
        )
        db.session.add(calendar_event)
        db.session.flush()

        task_item = task
        foreign_task_item = foreign_task

        comment = TaskItemComment(
            content='Comentario inicial',
            user_id=user.id,
            task_id=task_item.id,
        )
        foreign_comment = TaskItemComment(
            content='Comentario externo',
            user_id=outsider.id,
            task_id=foreign_task_item.id,
        )
        db.session.add_all([comment, foreign_comment])

        db.session.add(
            ProjectHistory(
                project_id=project.id,
                user_id=user.id,
                action_type='seed',
                action_description='Seed inicial de teste',
            )
        )
        db.session.commit()

        auditoria_area = AreaCatalog.query.filter_by(name='Auditoria').first()
        vpe_area = AreaCatalog.query.filter_by(name='VPE').first()

        return {
            'admin_id': admin.id,
            'user_id': user.id,
            'outsider_id': outsider.id,
            'editable_user_id': editable.id,
            'deletable_user_id': deletable.id,
            'project_id': project.id,
            'project_complete_id': project_complete.id,
            'foreign_project_id': foreign_project.id,
            'etapa_id': etapa.id,
            'etapa_started_id': etapa_started.id,
            'foreign_etapa_id': foreign_etapa.id,
            'task_id': task.id,
            'foreign_task_id': foreign_task.id,
            'orphan_task_id': orphan_task.id,
            'calendar_event_id': calendar_event.id,
            'task_item_id': task_item.id,
            'foreign_task_item_id': foreign_task_item.id,
            'comment_id': comment.id,
            'foreign_comment_id': foreign_comment.id,
            'template_id': template.id,
            'auditoria_area_id': auditoria_area.id if auditoria_area else None,
            'vpe_area_id': vpe_area.id if vpe_area else None,
            'user_username': user.username,
            'user_password': TEST_PASSWORD,
            'admin_username': admin.username,
            'admin_password': TEST_PASSWORD,
        }


@pytest.fixture
def client_admin(client, seed_data):
    _login(client, seed_data['admin_id'])
    return client


@pytest.fixture
def client_user(client, seed_data):
    _login(client, seed_data['user_id'])
    return client


@pytest.fixture
def client_outsider(client, seed_data):
    _login(client, seed_data['outsider_id'])
    return client


@pytest.fixture
def client_editable(client, seed_data):
    _login(client, seed_data['editable_user_id'])
    return client
