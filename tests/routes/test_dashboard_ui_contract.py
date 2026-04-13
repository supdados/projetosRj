import re
from pathlib import Path

from models import Project, db


def test_dashboard_recent_projects_renders_maximum_9_rows(app, client_user):
    with app.app_context():
        for index in range(1, 19):
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

    rendered_rows = re.findall(r'class="glass-table-row(?: [^"]+)?"', html)
    assert len(rendered_rows) == 15

    expected_visible_titles = [f'Dashboard Limit Test {index:02d}' for index in range(18, 3, -1)]
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


def test_dashboard_renders_chatbot_launcher_when_enabled(app, client_user):
    app.config.update(
        CHATBOT_ENABLED=True,
        CHATBOT_BASE_URL='https://chatbot.proderj.rj.gov.br',
    )

    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'dashboardChatbotLauncher',
        'dashboardChatbotPanel',
        'dashboardChatbotFrame',
        '/api/chatbot-token',
        'https://chatbot.proderj.rj.gov.br',
    ]

    for hook in required_hooks:
        assert hook in html


def test_dashboard_css_keeps_desktop_section_spacing_consistent():
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'index.css'
    css = css_path.read_text(encoding='utf-8')
    shared_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'style.css'
    shared_css = shared_css_path.read_text(encoding='utf-8')

    assert '.dashboard-page-v2 .dashboard-welcome-strip,\n        .dashboard-page-v2 .dashboard-kpi-row {\n            margin-bottom: 0.4rem !important;' in css
    assert '.dashboard-page-v2 .dashboard-welcome-strip,\n        .dashboard-page-v2 .dashboard-welcome-strip {\n            margin-bottom: 0.28rem !important;' not in css
    assert '.dashboard-page-v2 .dashboard-welcome-strip,\n        .dashboard-page-v2 .dashboard-kpi-row {\n            margin-bottom: 0.28rem !important;' in css
    assert '.dashboard-chatbot-launcher {' in shared_css
    assert '.dashboard-chatbot-panel {' in shared_css
