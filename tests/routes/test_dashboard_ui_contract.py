import re
from pathlib import Path

from models import Project, db
from tests._orgao_helpers import ensure_orgao


def test_dashboard_recent_projects_caps_rows_at_limit(app, client_user):
    # O painel "Projetos Recentes" (partials/_recent_projects_panel.html) lista
    # no máximo RECENT_PROJECTS_LIMIT (30) linhas <a class="rp-row">, as mais
    # recentes primeiro (ver routes/dashboard.py). As mais antigas ficam de fora.
    with app.app_context():
        for index in range(1, 36):
            project = Project(
                titulo=f"Dashboard Limit Test {index:02d}",
                orgao_id=ensure_orgao("Auditoria").id,
                orgao="Orgao Teste",
                prioridade="media",
                status="Vigente",
                objetivo_id=1,
                resultado_esperado_id=1,
                observacao="Projeto para contrato de limite da dashboard",
            )
            db.session.add(project)
        db.session.commit()

    response = client_user.get("/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    rendered_rows = re.findall(r'class="rp-row(?: [^"]+)?"', html)
    assert len(rendered_rows) == 30

    expected_visible_titles = [
        f"Dashboard Limit Test {index:02d}" for index in range(35, 5, -1)
    ]
    expected_hidden_titles = [
        f"Dashboard Limit Test {index:02d}" for index in range(1, 4)
    ]

    for title in expected_visible_titles:
        assert title in html

    for title in expected_hidden_titles:
        assert title not in html


def test_dashboard_template_contains_layout_and_scroll_hooks(client_user):
    response = client_user.get("/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        "dashboard-main-grid",
        "dashboard-recent-col",
        "dashboard-side-col",
        'id="dashboardRecentProjectsCard"',
        'id="dashboardTasksCard"',
        "glass-table-wrapper",
        "dashboard-tasks-kpi-card",
    ]

    for hook in required_hooks:
        assert hook in html


def test_dashboard_renders_chatbot_launcher_when_enabled(app, client_user):
    app.config.update(
        CHATBOT_ENABLED=True,
        CHATBOT_BASE_URL="https://chatbot.proderj.rj.gov.br",
    )

    response = client_user.get("/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        "dashboardChatbotLauncher",
        "dashboardChatbotPanel",
        "dashboardChatbotFrame",
        "/api/chatbot-token",
        "https://chatbot.proderj.rj.gov.br",
    ]

    for hook in required_hooks:
        assert hook in html


def test_dashboard_css_keeps_desktop_section_spacing_consistent():
    css_path = Path(__file__).resolve().parents[2] / "static" / "css" / "index.css"
    css = css_path.read_text(encoding="utf-8")
    shared_css_path = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "style.css"
    )
    shared_css = shared_css_path.read_text(encoding="utf-8")

    assert (
        ".dashboard-page-v2 .dashboard-welcome-strip,\n        .dashboard-page-v2 .dashboard-kpi-row {\n            margin-bottom: 0.4rem !important;"
        in css
    )
    assert (
        ".dashboard-page-v2 .dashboard-welcome-strip,\n        .dashboard-page-v2 .dashboard-welcome-strip {\n            margin-bottom: 0.28rem !important;"
        not in css
    )
    assert (
        ".dashboard-page-v2 .dashboard-welcome-strip,\n        .dashboard-page-v2 .dashboard-kpi-row {\n            margin-bottom: 0.28rem !important;"
        in css
    )
    assert ".dashboard-chatbot-launcher {" in shared_css
    assert ".dashboard-chatbot-panel {" in shared_css
