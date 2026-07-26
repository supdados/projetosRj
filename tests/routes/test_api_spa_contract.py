"""Testes de contrato dos endpoints JSON da SPA (envelope canônico).

Afirmam o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error":
{"code", "message"}}`` de ``/api/me``, ``/api/csrf-token`` e ``/api/dashboard``,
e o 401 JSON do guard ``api_login_required`` quando não há sessão.

Reutiliza as fixtures existentes de ``tests/conftest.py`` (``client`` anônimo e
``client_user`` autenticado + ``seed_data``). Sem mocks de rede: estes endpoints
operam sobre a sessão e o banco de teste já semeado.
"""

from __future__ import annotations

from typing import Any


def _assert_ok_envelope(payload: Any) -> dict[str, Any]:
    """Valida o envelope de sucesso e devolve o ``data``.

    Args:
        payload: Corpo JSON desempacotado da resposta.

    Returns:
        O conteúdo de ``data`` para asserções específicas do endpoint.
    """
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "data" in payload
    assert "error" not in payload
    return payload["data"]


def _assert_fail_envelope(payload: Any, *, code: str) -> None:
    """Valida o envelope de erro e o ``code`` canônico esperado."""
    assert isinstance(payload, dict)
    assert payload["ok"] is False
    assert "data" not in payload
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]


# ---------------------------------------------------------------------------
# /api/me
# ---------------------------------------------------------------------------


def test_api_me_returns_ok_envelope_with_safe_user_fields(client_user, seed_data):
    response = client_user.get("/api/me")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["id"] == seed_data["user_id"]
    assert set(data.keys()) == {
        "id",
        "name",
        "username",
        "is_admin",
        "orgaos",
        "auth_provider",
    }
    assert isinstance(data["orgaos"], list)
    assert data["auth_provider"] in {"govbr", "local"}


def test_api_me_expoe_papel_por_orgao(client_user, seed_data):
    """Cada vínculo de área carrega o papel; `is_admin` permanece no payload."""
    data = _assert_ok_envelope(client_user.get("/api/me").get_json())

    assert data["orgaos"]
    for orgao in data["orgaos"]:
        assert set(orgao.keys()) == {"id", "sigla", "nome", "papel"}
        assert orgao["papel"] == "gestor"
    assert data["is_admin"] is False


def test_api_me_never_serializes_secrets(client_user):
    data = _assert_ok_envelope(client_user.get("/api/me").get_json())
    assert "password_hash" not in data
    assert "govbr_refresh_token" not in data
    assert all("token" not in key for key in data)


def test_api_me_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/me")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


# ---------------------------------------------------------------------------
# /api/csrf-token
# ---------------------------------------------------------------------------


def test_api_csrf_token_returns_ok_envelope_with_token(client_user):
    response = client_user.get("/api/csrf-token")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["token"], str)
    assert data["token"]


def test_api_csrf_token_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/csrf-token")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


# ---------------------------------------------------------------------------
# /api/dashboard
# ---------------------------------------------------------------------------


def test_api_dashboard_returns_ok_envelope_with_expected_shape(client_user):
    response = client_user.get("/api/dashboard")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["recent_projects"], list)
    assert isinstance(data["recent_tasks"], list)
    assert "counts" in data
    assert "projects" in data["counts"]
    assert "tasks" in data["counts"]
    assert "total" in data["counts"]["projects"]


def test_api_dashboard_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/dashboard")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_dashboard_invalid_orgao_filter_returns_422_envelope(client_user):
    """Filtro de órgão fora do escopo do usuário => 422 ``validation`` (não 302)."""
    response = client_user.get("/api/dashboard?orgao=999999")

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")
