import re

from models import Project, db


def test_dashboard_recent_projects_renders_maximum_9_rows(app, client_user):
    with app.app_context():
        for index in range(1, 13):
            project = Project(
                titulo=f'Dashboard Limit Test {index:02d}',
                area_responsavel='Auditoria',
                orgao='Orgao Teste',
                prioridade='media',
                status='Vigente',
                objetivo_id=1,
                resultado_esperado_id=1,
                observacao='Projeto para contrato de limite da dashboard',
            )
            db.session.add(project)
        db.session.commit()

    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    rendered_rows = re.findall(r'class="glass-table-row"', html)
    assert len(rendered_rows) == 9

    expected_visible_titles = [f'Dashboard Limit Test {index:02d}' for index in range(12, 3, -1)]
    expected_hidden_titles = [f'Dashboard Limit Test {index:02d}' for index in range(1, 4)]

    for title in expected_visible_titles:
        assert title in html

    for title in expected_hidden_titles:
        assert title not in html


def test_dashboard_template_contains_layout_and_scroll_hooks(client_user):
    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'dashboard-main-grid',
        'dashboard-recent-col',
        'dashboard-side-col',
        'id="dashboardRecentProjectsCard"',
        'id="dashboardTasksCard"',
        'glass-table-wrapper',
        'dashboard-tasks-kpi-card',
    ]

    for hook in required_hooks:
        assert hook in html
