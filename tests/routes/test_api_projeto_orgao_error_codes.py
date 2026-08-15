"""Erro TIPADO do validador de órgão e o status HTTP que ``POST /api/projetos``
deriva dele.

Antes o status vinha de ``"permissão" in msg.lower()``; agora vem do ``code`` de
``OrgaoResolutionError``. Estes testes travam os dois lados: os códigos que o
validador emite e o contrato HTTP (403 forbidden / 422 validation) da rota.
"""

from __future__ import annotations

from flask import g

from models import User, db
from routes.projects.crud import _resolve_orgao_from_form


def _login_g(app, user_id: int):
    """Contexto de request com ``g.user`` carregado (o validador lê ``g.user``)."""
    ctx = app.test_request_context()
    ctx.push()
    g.user = db.session.get(User, user_id)
    return ctx


# ── Validador: códigos tipados ────────────────────────────────────────────────


def test_resolve_orgao_forbidden_code(app, seed_data):
    ctx = _login_g(app, seed_data["outsider_id"])
    try:
        orgao, error = _resolve_orgao_from_form(seed_data["auditoria_orgao_id"])
    finally:
        ctx.pop()
    assert orgao is None
    assert error.code == "forbidden"
    assert "permissão" in error.message


def test_resolve_orgao_not_found_code(app, seed_data):
    ctx = _login_g(app, seed_data["user_id"])
    try:
        orgao, error = _resolve_orgao_from_form(999999)
    finally:
        ctx.pop()
    assert orgao is None
    assert error.code == "not_found"


def test_resolve_orgao_validation_codes(app, seed_data):
    ctx = _login_g(app, seed_data["user_id"])
    try:
        _, missing = _resolve_orgao_from_form(None)
        _, invalid = _resolve_orgao_from_form("abc")
    finally:
        ctx.pop()
    assert missing.code == "validation"
    assert invalid.code == "validation"


def test_resolve_orgao_success_has_no_error(app, seed_data):
    ctx = _login_g(app, seed_data["user_id"])
    try:
        orgao, error = _resolve_orgao_from_form(seed_data["auditoria_orgao_id"])
    finally:
        ctx.pop()
    assert error is None
    assert orgao.id == seed_data["auditoria_orgao_id"]


# ── Rota: mapeamento código → status (contrato preservado) ────────────────────


def test_api_projeto_criar_orgao_sem_permissao_403(client_outsider, seed_data):
    response = client_outsider.post(
        "/api/projetos",
        json={"titulo": "Fora do escopo", "orgao_id": seed_data["auditoria_orgao_id"]},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_api_projeto_criar_orgao_ausente_422(client_user, seed_data):
    response = client_user.post("/api/projetos", json={"titulo": "Sem órgão"})
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["error"]["code"] == "validation"
    assert "órgão" in payload["error"]["message"]


def test_api_projeto_criar_orgao_invalido_422(client_user, seed_data):
    response = client_user.post(
        "/api/projetos", json={"titulo": "Órgão texto", "orgao_id": "abc"}
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"


def test_api_projeto_criar_orgao_inexistente_422(client_user, seed_data):
    response = client_user.post(
        "/api/projetos", json={"titulo": "Órgão fantasma", "orgao_id": 999999}
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"
