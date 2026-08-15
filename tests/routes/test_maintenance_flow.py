"""Cobertura de /favicon.ico em routes/maintenance.py.

Verifica headers de cache, tipo de conteúdo e acesso público (sem login).
"""


def test_favicon_returns_icon_with_no_cache_headers(client):
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.mimetype == "image/vnd.microsoft.icon"
    assert (
        response.headers.get("Cache-Control") == "no-cache, no-store, must-revalidate"
    )
    assert response.headers.get("Pragma") == "no-cache"
    assert response.headers.get("Expires") == "0"


def test_favicon_available_without_authentication(client):
    # Favicon é público: mesmo sem login, retorna 200.
    response = client.get("/favicon.ico")
    assert response.status_code == 200
