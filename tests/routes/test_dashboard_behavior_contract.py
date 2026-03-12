import datetime

from flask import jsonify

import routes.dashboard as dashboard_routes
from models import CalendarEvent, Etapa, Project, ProjectStageMeeting, Task, db


def _capture_dashboard_context(monkeypatch):
    captured = {}

    def fake_render_template(template_name, **context):
        captured['template_name'] = template_name
        captured['context'] = context
        return jsonify({'ok': True})

    monkeypatch.setattr(dashboard_routes, 'render_template', fake_render_template)
    return captured


def test_dashboard_context_for_user_scopes_projects_tasks_and_overdue(app, client_user, seed_data, monkeypatch):
    with app.app_context():
        db.session.add(
            Project(
                titulo='Projeto Auditoria Finalizado',
                area_responsavel='Auditoria',
                orgao='Orgao Dashboard',
                prioridade='baixa',
                status='Finalizado',
                objetivo_id=1,
                resultado_esperado_id=1,
            )
        )
        db.session.add_all(
            [
                Task(
                    descricao='Tarefa Auditoria Validacao',
                    status='para_validacao',
                    prioridade='alta',
                    project_id=seed_data['project_id'],
                    created_by_id=seed_data['user_id'],
                ),
                Task(
                    descricao='Tarefa Auditoria Ajustes',
                    status='para_ajustes',
                    prioridade='urgente',
                    project_id=seed_data['project_complete_id'],
                    created_by_id=seed_data['user_id'],
                ),
                Task(
                    descricao='Tarefa VPD Oculta Dashboard',
                    status='em_andamento',
                    prioridade='urgente',
                    project_id=seed_data['foreign_project_id'],
                    created_by_id=seed_data['outsider_id'],
                ),
                Task(
                    descricao='Tarefa Arquivada Dashboard',
                    status='em_andamento',
                    prioridade='alta',
                    project_id=seed_data['project_id'],
                    created_by_id=seed_data['user_id'],
                    is_archived=True,
                ),
            ]
        )
        db.session.commit()

    captured = _capture_dashboard_context(monkeypatch)

    response = client_user.get('/dashboard')

    assert response.status_code == 200
    assert captured['template_name'] == 'index.html'
    context = captured['context']

    assert context['num_projects'] == 3
    assert context['count_vigente'] == 2
    assert context['count_finalizado'] == 1
    assert context['count_alta'] == 1
    assert context['count_media'] == 1
    assert context['count_baixa'] == 1
    assert context['projetos_em_atraso'] == 1

    assert context['dashboard_open_tasks_count'] == 4
    assert context['dashboard_open_items_count'] == 4
    assert context['task_items_nao_iniciada'] == 2
    assert context['task_items_para_validacao'] == 1
    assert context['task_items_para_ajustes'] == 1
    assert context['task_items_total'] == 4
    assert context['task_atencao_count'] == 2
    assert context['task_urgente_count'] == 1
    assert context['task_alta_count'] == 1

    recent_project_titles = [project.titulo for project in context['recent_projects']]
    assert 'Projeto VPD' not in recent_project_titles

    recent_task_titles = [task.descricao for task in context['recent_tasks']]
    assert 'Tarefa Auditoria Validacao' in recent_task_titles
    assert 'Tarefa Auditoria Ajustes' in recent_task_titles
    assert 'Tarefa VPD Oculta Dashboard' not in recent_task_titles
    assert 'Tarefa Arquivada Dashboard' not in recent_task_titles


def test_dashboard_admin_area_filter_restricts_projects_and_tasks(app, client_admin, seed_data, monkeypatch):
    with app.app_context():
        db.session.add(
            Task(
                descricao='Tarefa Extra Auditoria Dashboard',
                status='em_andamento',
                prioridade='alta',
                project_id=seed_data['project_id'],
                created_by_id=seed_data['admin_id'],
            )
        )
        db.session.commit()

    captured = _capture_dashboard_context(monkeypatch)

    response = client_admin.get('/dashboard', query_string={'area': 'VPD'})

    assert response.status_code == 200
    context = captured['context']

    assert context['num_projects'] == 1
    assert context['count_vigente'] == 1
    assert context['count_finalizado'] == 0
    assert context['projetos_em_atraso'] == 1
    assert context['dashboard_open_tasks_count'] == 1
    assert context['task_items_em_andamento'] == 1
    assert context['task_items_total'] == 1

    recent_project_titles = [project.titulo for project in context['recent_projects']]
    assert recent_project_titles == ['Projeto VPD']

    recent_task_titles = [task.descricao for task in context['recent_tasks']]
    assert recent_task_titles == ['Item VPD']


def test_dashboard_redirects_when_non_admin_forces_foreign_area(client, seed_data):
    with client.session_transaction() as session:
        session['user_id'] = seed_data['deletable_user_id']

    response = client.get('/dashboard', query_string={'area': 'SUBEDD'}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/dashboard')


def test_dashboard_overdue_count_ignores_google_meeting_only_project(app, client_user, seed_data, monkeypatch):
    with app.app_context():
        project = Project(
            titulo='Projeto Apenas Reuniao',
            area_responsavel='Auditoria',
            orgao='Orgao Dashboard',
            prioridade='media',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(project)
        db.session.flush()

        event = CalendarEvent(
            user_id=seed_data['user_id'],
            title='Reunião atrasada informativa',
            starts_at=datetime.datetime(2026, 1, 5, 13, 0),
            ends_at=datetime.datetime(2026, 1, 5, 14, 0),
            source='app',
            google_event_id='google-dashboard-ignore',
            google_calendar_id='primary',
            sync_status='ok',
        )
        etapa = Etapa(
            descricao='Reunião atrasada informativa',
            data_inicio=datetime.date(2026, 1, 5),
            data_fim=datetime.date(2026, 1, 5),
            responsavel='user@example.com',
            project_id=project.id,
            ordem=0,
            entry_type='google_meeting',
        )
        db.session.add_all([event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=project.id,
                calendar_event_id=event.id,
                creator_user_id=seed_data['user_id'],
                google_owner_account_id='google-dashboard-ignore',
                google_owner_email='user@example.com',
                google_event_id='google-dashboard-ignore',
                google_calendar_id='primary',
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                timezone='America/Sao_Paulo',
                sync_status='ok',
            )
        )
        db.session.commit()

    captured = _capture_dashboard_context(monkeypatch)

    response = client_user.get('/dashboard')

    assert response.status_code == 200
    context = captured['context']
    assert context['num_projects'] == 3
    assert context['projetos_em_atraso'] == 1
