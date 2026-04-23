"""Testes unitários das propriedades Project.workflow_etapas / total_workflow_etapas /
todas_etapas_concluidas.

Essas propriedades filtram etapas do tipo `google_meeting` para computar o
progresso real do projeto (que ignora reuniões) e são consultadas em várias
rotas e templates — regredir seu comportamento corromperia a barra de progresso.
"""

import datetime

from models import Etapa, Project, db
from tests._orgao_helpers import ensure_orgao


def _project(titulo='Projeto WF'):
    project = Project(
        titulo=titulo,
        orgao_id=ensure_orgao('Auditoria').id,
        orgao='Orgao A',
        prioridade='media',
        status='Vigente',
        objetivo_id=1,
        resultado_esperado_id=1,
    )
    db.session.add(project)
    db.session.flush()
    return project


def _etapa(project, *, descricao, ordem=0, iniciada=False, done=False, entry_type='manual'):
    etapa = Etapa(
        descricao=descricao,
        data_inicio=datetime.date(2026, 1, 10),
        data_fim=datetime.date(2026, 1, 15),
        responsavel='Resp',
        iniciada=iniciada,
        done=done,
        comentarios='',
        project_id=project.id,
        ordem=ordem,
        entry_type=entry_type,
    )
    db.session.add(etapa)
    return etapa


def test_workflow_etapas_filters_out_google_meetings(app):
    with app.app_context():
        project = _project()
        _etapa(project, descricao='Planejamento', ordem=0)
        _etapa(project, descricao='Reunião kickoff', ordem=1, entry_type='google_meeting')
        _etapa(project, descricao='Execução', ordem=2)
        db.session.commit()

        workflow = project.workflow_etapas
        assert [e.descricao for e in workflow] == ['Planejamento', 'Execução']
        assert project.total_workflow_etapas == 2


def test_workflow_etapas_empty_when_project_has_no_etapas(app):
    with app.app_context():
        project = _project()
        db.session.commit()

        assert project.workflow_etapas == []
        assert project.total_workflow_etapas == 0


def test_workflow_etapas_only_google_meetings_returns_empty(app):
    with app.app_context():
        project = _project()
        _etapa(project, descricao='Reunião 1', ordem=0, entry_type='google_meeting')
        _etapa(project, descricao='Reunião 2', ordem=1, entry_type='google_meeting')
        db.session.commit()

        assert project.workflow_etapas == []
        assert project.total_workflow_etapas == 0


def test_todas_etapas_concluidas_ignores_google_meetings(app):
    with app.app_context():
        project = _project()
        _etapa(project, descricao='Fase A', ordem=0, iniciada=True, done=True)
        _etapa(project, descricao='Fase B', ordem=1, iniciada=True, done=True)
        # Meeting não iniciada nem concluída: não deve impedir o status de "todas concluídas".
        _etapa(
            project, descricao='Reunião', ordem=2,
            iniciada=False, done=False, entry_type='google_meeting',
        )
        db.session.commit()

        assert project.todas_etapas_concluidas is True


def test_todas_etapas_concluidas_false_when_workflow_item_pending(app):
    with app.app_context():
        project = _project()
        _etapa(project, descricao='Fase A', ordem=0, iniciada=True, done=True)
        _etapa(project, descricao='Fase B', ordem=1, iniciada=True, done=False)
        db.session.commit()

        assert project.todas_etapas_concluidas is False


def test_todas_etapas_concluidas_false_when_no_workflow_etapas(app):
    with app.app_context():
        project = _project()
        # Apenas uma reunião — ainda não há workflow a concluir.
        _etapa(project, descricao='Reunião', ordem=0, entry_type='google_meeting')
        db.session.commit()

        assert project.todas_etapas_concluidas is False


def test_data_inicio_e_fim_do_projeto_consideram_todas_etapas(app):
    """Os campos data_inicio_projeto/data_fim_projeto usam TODAS as etapas
    (inclusive reuniões) — documentado aqui para prevenir regressão."""
    with app.app_context():
        project = _project()
        _etapa(project, descricao='A', ordem=0)  # 2026-01-10 → 2026-01-15
        etapa_meet = _etapa(
            project, descricao='Reunião prévia', ordem=1, entry_type='google_meeting',
        )
        etapa_meet.data_inicio = datetime.date(2026, 1, 5)
        etapa_meet.data_fim = datetime.date(2026, 1, 6)
        db.session.commit()

        assert project.data_inicio_projeto == datetime.date(2026, 1, 5)
        assert project.data_fim_projeto == datetime.date(2026, 1, 15)
