"""Contrato do path nativo ``/dashboard`` apos o cut-over KEEP-ENDPOINT.

Antes esta tela renderizava o template Jinja ``index.html`` com paineis de
projetos recentes/KPIs. Agora ``main.dashboard`` mantem o mesmo endpoint (para
preservar os ``url_for("main.dashboard")`` em auth/decorators/crud) mas serve a
shell da SPA SvelteKit via ``_render_spa()``. A fonte de dados real do dashboard
vive em ``GET /api/dashboard`` (coberto por ``test_api_spa_contract`` e
``test_dashboard_behavior_contract``). Estes testes apenas garantem que o path
nativo continua servindo a SPA (200 logado) e o shell correto.
"""


def test_dashboard_serves_spa_shell_when_logged_in(client_user):
    response = client_user.get("/dashboard")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert "data-sveltekit-preload-data" in body
    assert '<meta name="csrf-token"' in body


def test_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
