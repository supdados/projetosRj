"""Testes de contrato do shell da SPA (routes/spa.py).

Afirmam que ``/spa`` e ``/spa/<subpath>`` servem o index do bundle via Jinja
(com ``<meta name="csrf-token">`` e o ``csp_nonce`` no script de bootstrap), e
que a rota NÃO intercepta áreas reservadas (``/api/*``, ``/login``, ``/webhook``,
etc.) — essas continuam respondendo nas suas rotas originais.
"""

from __future__ import annotations


def _csp_script_src(response) -> str:
    """Extrai a diretiva ``script-src`` do header CSP da resposta."""
    csp = response.headers.get("Content-Security-Policy", "")
    for directive in csp.split(";"):
        directive = directive.strip()
        if directive.startswith("script-src"):
            return directive
    return ""


def test_spa_root_serves_html_with_csrf_meta(client):
    response = client.get("/spa")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert '<meta name="csrf-token"' in body
    assert "data-sveltekit-preload-data" in body


def test_spa_bootstrap_script_uses_csp_nonce(client):
    response = client.get("/spa")
    body = response.get_data(as_text=True)

    script_src = _csp_script_src(response)
    assert "'nonce-" in script_src
    # O nonce do header deve casar com o nonce injetado no <script>.
    nonce = script_src.split("'nonce-", 1)[1].split("'", 1)[0]
    assert nonce
    assert f'nonce="{nonce}"' in body
    # O placeholder do bundle deve ter sido substituido (não vaza literal).
    assert "%CSP_NONCE%" not in body


def test_response_sets_anti_clickjacking_headers(client):
    """Regressão do achado de Clickjacking (CWE-1021): X-Frame-Options: DENY e
    CSP com frame-ancestors 'none' — impedem a página de ser embutida em iframe."""
    response = client.get("/spa")

    assert response.headers.get("X-Frame-Options") == "DENY"
    csp = response.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp


def test_spa_subpath_dashboard_serves_same_shell(client):
    response = client.get("/spa/dashboard")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "data-sveltekit-preload-data" in response.get_data(as_text=True)


def test_colecoes_paths_serve_spa_shell(client):
    """Índice e página interna de Coleções resolvem no deep-link/F5 (catch-all)."""
    for path in ("/colecoes", "/colecoes/12"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "data-sveltekit-preload-data" in response.get_data(as_text=True)


def test_colecoes_non_numeric_id_is_not_served(client):
    """Só ``colecoes/<numero>`` é migrado; qualquer outro sufixo segue 404."""
    assert client.get("/colecoes/abc").status_code == 404


def test_spa_reserved_subpath_is_not_intercepted(client):
    """Um subpath reservado sob /spa é rejeitado (404), não servido como shell."""
    response = client.get("/spa/api/me")
    assert response.status_code == 404


def test_spa_route_does_not_capture_api_or_login(client):
    """Rotas reservadas seguem nas suas próprias views (não no shell da SPA)."""
    # /api/me sem sessão => 401 JSON (api_login_required), não o shell HTML.
    api_response = client.get("/api/me")
    assert api_response.status_code == 401
    assert api_response.is_json

    # /login => página de login (200 HTML), nunca o shell da SPA.
    login_response = client.get("/login")
    assert login_response.status_code == 200
    assert "data-sveltekit-preload-data" not in login_response.get_data(as_text=True)
