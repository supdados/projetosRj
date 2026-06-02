import datetime
import os

import pytest
from sqlalchemy.pool import NullPool

os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from app import create_app
from models import (
    CalendarEvent,
    Etapa,
    IndicadorProjeto,
    OrgaoUnidade,
    OrgaoTipo,
    Project,
    ProjectHistory,
    StageTemplate,
    StageTemplateItem,
    Task,
    TaskItem,
    TaskItemComment,
    User,
    UserOrgao,
    db,
)
from catalogs.objectives import sync_goal_catalog_to_db
from routes.orgao_tree import backfill_orgao_tipo_ids, ensure_default_orgao_tipos

TEST_PASSWORD = "senha123"


def _ensure_setd():
    setd = OrgaoUnidade.query.filter_by(sigla="SETD").first()
    if setd is None:
        setd = OrgaoUnidade(
            sigla="SETD", nome="SETD", tipo="Secretaria", pai_id=None, ordem=0
        )
        db.session.add(setd)
        db.session.flush()
    return setd


def _ensure_orgao(sigla):
    existing = OrgaoUnidade.query.filter(
        db.func.lower(OrgaoUnidade.sigla) == sigla.lower()
    ).first()
    if existing is not None:
        return existing
    setd = _ensure_setd()
    orgao = OrgaoUnidade(
        sigla=sigla,
        nome=sigla,
        tipo="Subsecretaria",
        pai_id=setd.id,
        ordem=0,
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _create_user(
    username, name, *, is_admin=False, orgao_siglas=None, orgao="Orgao Teste"
):
    user = User(
        username=username,
        name=name,
        orgao=orgao,
        is_admin=is_admin,
    )
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.flush()

    for sigla in orgao_siglas or []:
        orgao_unit = _ensure_orgao(sigla)
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_unit.id))

    return user


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.sqlite"
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": True,
            "WTF_CSRF_ENABLED": False,
            # Isola os testes do .env do desenvolvedor: features opcionais
            # ficam desligadas por padrão e cada teste que precisa delas liga
            # explicitamente via app.config.update(...).
            "CHATBOT_ENABLED": False,
            "GOVBR_OIDC_ENABLED": False,
        }
    )

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
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
        ensure_default_orgao_tipos()
        admin = _create_user(
            "admin", "Administrador", is_admin=True, orgao_siglas=["Auditoria"]
        )
        user = _create_user(
            "user_auditoria", "Usuario Auditoria", orgao_siglas=["Auditoria"]
        )
        outsider = _create_user("user_vpd", "Usuario VPD", orgao_siglas=["VPD"])
        editable = _create_user(
            "user_editavel", "Usuario Editavel", orgao_siglas=["Auditoria"]
        )
        deletable = _create_user(
            "user_deletavel", "Usuario Deletavel", orgao_siglas=["SUPDADOS"]
        )

        template = StageTemplate(
            name="Template Base", description="Template inicial de teste"
        )
        db.session.add(template)
        db.session.flush()
        db.session.add_all(
            [
                StageTemplateItem(
                    name="Planejamento",
                    duration_days=2,
                    order=0,
                    templateId=template.id,
                ),
                StageTemplateItem(
                    name="Execucao", duration_days=3, order=1, templateId=template.id
                ),
            ]
        )

        auditoria_orgao = _ensure_orgao("Auditoria")
        project = Project(
            titulo="Projeto Auditoria",
            orgao_id=auditoria_orgao.id,
            orgao="Orgao A",
            prioridade="alta",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
            observacao="Projeto principal para testes",
        )
        db.session.add(project)
        db.session.flush()
        db.session.add(IndicadorProjeto(project_id=project.id, indicador_id=1))

        etapa = Etapa(
            descricao="Etapa Planejada",
            data_inicio=datetime.date(2026, 1, 10),
            data_fim=datetime.date(2026, 1, 15),
            responsavel="Usuario Auditoria",
            iniciada=False,
            done=False,
            comentarios="Sem comentarios",
            project_id=project.id,
            ordem=0,
        )
        etapa_started = Etapa(
            descricao="Etapa Iniciada",
            data_inicio=datetime.date(2026, 1, 16),
            data_fim=datetime.date(2026, 1, 20),
            responsavel="Usuario Auditoria",
            iniciada=True,
            done=False,
            comentarios="Em andamento",
            project_id=project.id,
            ordem=1,
        )
        db.session.add_all([etapa, etapa_started])

        project_complete = Project(
            titulo="Projeto Concluivel",
            orgao_id=auditoria_orgao.id,
            orgao="Orgao A",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
            observacao="Projeto pronto para concluir",
        )
        db.session.add(project_complete)
        db.session.flush()
        db.session.add(
            Etapa(
                descricao="Etapa Finalizada",
                data_inicio=datetime.date(2026, 2, 1),
                data_fim=datetime.date(2026, 2, 3),
                responsavel="Usuario Auditoria",
                iniciada=True,
                done=True,
                comentarios="Concluida",
                project_id=project_complete.id,
                ordem=0,
            )
        )

        vpd_orgao = _ensure_orgao("VPD")
        vpe_orgao = _ensure_orgao("VPE")
        foreign_project = Project(
            titulo="Projeto VPD",
            orgao_id=vpd_orgao.id,
            orgao="Orgao B",
            prioridade="baixa",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
            observacao="Projeto para teste de permissao",
        )
        db.session.add(foreign_project)
        db.session.flush()
        foreign_etapa = Etapa(
            descricao="Etapa VPD",
            data_inicio=datetime.date(2026, 1, 5),
            data_fim=datetime.date(2026, 1, 12),
            responsavel="Usuario VPD",
            iniciada=True,
            done=False,
            comentarios="Etapa area VPD",
            project_id=foreign_project.id,
            ordem=0,
        )
        db.session.add(foreign_etapa)

        task = Task(
            descricao="Item Auditoria",
            status="nao_iniciada",
            responsavel="Usuario Auditoria",
            ordem=1,
            project_id=project.id,
            created_by_id=user.id,
        )
        foreign_task = Task(
            descricao="Item VPD",
            status="em_andamento",
            responsavel="Usuario VPD",
            ordem=1,
            project_id=foreign_project.id,
            created_by_id=outsider.id,
        )
        orphan_task = Task(
            descricao="Tarefa Sem Projeto",
            status="nao_iniciada",
            ordem=1,
            project_id=None,
            created_by_id=user.id,
        )
        db.session.add_all([task, foreign_task, orphan_task])
        db.session.flush()

        calendar_event = CalendarEvent(
            user_id=user.id,
            title="Evento Seed",
            description="Evento inicial de calendário para testes",
            location="Sala 101",
            starts_at=datetime.datetime(2026, 3, 10, 12, 0),
            ends_at=datetime.datetime(2026, 3, 10, 13, 0),
            source="app",
            sync_status="pending",
        )
        db.session.add(calendar_event)
        db.session.flush()

        task_item = task
        foreign_task_item = foreign_task

        comment = TaskItemComment(
            content="Comentario inicial",
            user_id=user.id,
            task_id=task_item.id,
        )
        foreign_comment = TaskItemComment(
            content="Comentario externo",
            user_id=outsider.id,
            task_id=foreign_task_item.id,
        )
        db.session.add_all([comment, foreign_comment])

        db.session.add(
            ProjectHistory(
                project_id=project.id,
                user_id=user.id,
                action_type="seed",
                action_description="Seed inicial de teste",
            )
        )

        orgao_root = OrgaoUnidade(
            nome="Estado do Rio de Janeiro",
            sigla="ERJ",
            tipo="Estado",
            pai_id=None,
            ordem=0,
            ativo=True,
        )
        db.session.add(orgao_root)
        db.session.flush()
        orgao_secretaria = OrgaoUnidade(
            nome="Secretaria de Testes",
            sigla="SECT",
            tipo="Secretaria",
            pai_id=orgao_root.id,
            ordem=0,
            ativo=True,
        )
        db.session.add(orgao_secretaria)
        db.session.flush()

        backfill_orgao_tipo_ids()
        secretaria_tipo = OrgaoTipo.query.filter_by(nome="Secretaria").first()
        nucleo_tipo = OrgaoTipo.query.filter_by(nome="Núcleo").first()

        db.session.commit()

        return {
            "admin_id": admin.id,
            "user_id": user.id,
            "outsider_id": outsider.id,
            "editable_user_id": editable.id,
            "deletable_user_id": deletable.id,
            "project_id": project.id,
            "project_complete_id": project_complete.id,
            "foreign_project_id": foreign_project.id,
            "etapa_id": etapa.id,
            "etapa_started_id": etapa_started.id,
            "foreign_etapa_id": foreign_etapa.id,
            "task_id": task.id,
            "foreign_task_id": foreign_task.id,
            "orphan_task_id": orphan_task.id,
            "calendar_event_id": calendar_event.id,
            "task_item_id": task_item.id,
            "foreign_task_item_id": foreign_task_item.id,
            "comment_id": comment.id,
            "foreign_comment_id": foreign_comment.id,
            "template_id": template.id,
            "auditoria_orgao_id": auditoria_orgao.id,
            "vpd_orgao_id": vpd_orgao.id,
            "vpe_orgao_id": vpe_orgao.id,
            "orgao_root_id": orgao_root.id,
            "orgao_child_id": orgao_secretaria.id,
            "orgao_tipo_secretaria_id": secretaria_tipo.id if secretaria_tipo else 2,
            "orgao_tipo_nucleo_id": nucleo_tipo.id if nucleo_tipo else 11,
            "user_username": user.username,
            "user_password": TEST_PASSWORD,
            "admin_username": admin.username,
            "admin_password": TEST_PASSWORD,
        }


# Cada cliente autenticado cria seu PRÓPRIO test_client com cookie jar
# independente. Compartilhar o `client` único fazia o 2º login sobrescrever a
# sessão do 1º, mascarando os 403 esperados quando dois usuários distintos são
# pedidos no mesmo teste (P1b — defeito de fixture, produção está correta).
@pytest.fixture
def client_admin(app, seed_data):
    c = app.test_client()
    _login(c, seed_data["admin_id"])
    return c


@pytest.fixture
def client_user(app, seed_data):
    c = app.test_client()
    _login(c, seed_data["user_id"])
    return c


@pytest.fixture
def client_outsider(app, seed_data):
    c = app.test_client()
    _login(c, seed_data["outsider_id"])
    return c


@pytest.fixture
def client_editable(app, seed_data):
    c = app.test_client()
    _login(c, seed_data["editable_user_id"])
    return c
