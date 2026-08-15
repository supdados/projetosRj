"""Testes de contrato do shell da SPA (routes/spa.py).

O shell tem FONTE UNICA (``frontend/src/app.html``): o build emite
``static/spa/index.html`` e ``_render_spa()`` o serve substituindo os
placeholders ``%CSP_NONCE%``/``%CSRF_TOKEN%``/``%CHATBOT_BASE_URL%`` em
runtime. Afirmam tambem que o catch-all NAO intercepta areas reservadas
(``/api/*``, ``/login``, ``/webhook``, etc.) e que a reserva casa por
segmento completo (``/apiario`` nao e bloqueado nem servido).
"""

from __future__ import annotations

import os
import re

import pytest
from werkzeug.exceptions import InternalServerError

import routes.spa as spa_module

requires_spa_build = pytest.mark.skipif(
    not (
        os.path.exists(spa_module._BUNDLE_INDEX_PATH)
        and os.path.exists(spa_module._ROUTE_MANIFEST_PATH)
    ),
    reason="requer bundle da SPA (npm run build em frontend/)",
)


def _csp_script_src(response) -> str:
    """Extrai a diretiva ``script-src`` do header CSP da resposta."""
    csp = response.headers.get("Content-Security-Policy", "")
    for directive in csp.split(";"):
        directive = directive.strip()
        if directive.startswith("script-src"):
            return directive
    return ""


@requires_spa_build
def test_spa_bootstrap_script_uses_csp_nonce(client):
    response = client.get("/colecoes")
    body = response.get_data(as_text=True)

    script_src = _csp_script_src(response)
    assert "'nonce-" in script_src
    # O nonce do header deve casar com o nonce injetado no <script>.
    nonce = script_src.split("'nonce-", 1)[1].split("'", 1)[0]
    assert nonce
    assert f'nonce="{nonce}"' in body
    # O placeholder do bundle deve ter sido substituido (não vaza literal).
    assert "%CSP_NONCE%" not in body


@requires_spa_build
def test_spa_shell_injects_real_csrf_token(client):
    """A meta csrf-token sai com token vivo (client.ts manda em X-CSRFToken)."""
    body = client.get("/colecoes").get_data(as_text=True)

    assert "%CSRF_TOKEN%" not in body
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', body)
    assert match and match.group(1)


@requires_spa_build
def test_spa_shell_reconciles_theme_and_brand_head(client):
    """Anti-flash seta data-theme E data-bs-theme; favicons/FontAwesome no shell unico."""
    body = client.get("/colecoes").get_data(as_text=True)

    assert "data-bs-theme" in body
    assert "'data-theme'" in body or "data-theme" in body
    assert "/static/favicon.ico" in body
    assert "/static/vendor/fontawesome/css/all.min.css" in body
    # Chatbot desligado nos testes: placeholder substituido por vazio.
    assert "%CHATBOT_BASE_URL%" not in body


def test_response_sets_anti_clickjacking_headers(client):
    """Regressão do achado de Clickjacking (CWE-1021): X-Frame-Options: DENY e
    CSP com frame-ancestors 'none' — impedem a página de ser embutida em iframe."""
    response = client.get("/colecoes")

    assert response.headers.get("X-Frame-Options") == "DENY"
    csp = response.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp


@requires_spa_build
def test_colecoes_paths_serve_spa_shell(client):
    """Índice e página interna de Coleções resolvem no deep-link/F5 (catch-all)."""
    for path in ("/colecoes", "/colecoes/12"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.mimetype == "text/html", path
        body = response.get_data(as_text=True)
        assert '<meta name="csrf-token"' in body, path
        assert "data-sveltekit-preload-data" in body, path


def test_colecoes_non_numeric_id_is_not_served(client):
    """Só ``colecoes/<numero>`` é migrado; qualquer outro sufixo segue 404."""
    assert client.get("/colecoes/abc").status_code == 404


def test_admin_root_without_page_is_clean_404(client):
    """``/admin`` não tem +page.svelte: fora do manifesto → 404 do Flask (não
    a shell com o 404 do SvelteKit em HTTP 200)."""
    assert client.get("/admin").status_code == 404


def test_spa_reserved_subpath_is_not_intercepted(client):
    """Subpath com prefixo reservado é rejeitado (404) pelo catch-all da SPA."""
    response = client.get("/spa/api/me")
    assert response.status_code == 404


def test_reserved_prefix_matches_full_segment_only(client):
    """``api`` reserva /api e /api/*, não /apiario (match por segmento)."""
    assert spa_module._is_reserved("api") is True
    assert spa_module._is_reserved("api/me") is True
    assert spa_module._is_reserved("apiario") is False
    assert spa_module._is_reserved("loginhistory") is False
    # Não-reservado e fora do manifesto → 404 igual.
    assert client.get("/apiario").status_code == 404


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


@requires_spa_build
def test_missing_bundle_fails_loud_with_build_hint(client, monkeypatch):
    """Sem o index buildado: 503 com instrução explícita, nunca 404 silencioso."""
    monkeypatch.setattr(spa_module, "_BUNDLE_INDEX_PATH", "/nonexistent/spa/index.html")
    response = client.get("/colecoes")
    assert response.status_code == 503
    assert "npm run build" in response.get_data(as_text=True)


def test_missing_csp_nonce_aborts_500(app):
    """Sem g.csp_nonce o serving falha alto — não gera um segundo nonce."""
    from flask import g

    with app.test_request_context("/projetos"):
        if hasattr(g, "csp_nonce"):
            delattr(g, "csp_nonce")
        with pytest.raises(InternalServerError):
            spa_module._require_csp_nonce()
