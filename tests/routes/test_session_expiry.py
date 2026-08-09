"""Regressão do tempo de vida da sessão: refresh Gov.br best-effort + teto absoluto.

Cobre dois comportamentos que se equilibram em ``app.py``:

- ``refresh_govbr_token_best_effort`` NUNCA desloga — sem refresh token, com erro
  do IdP ou com resposta sem ``expires_in``, ele desiste e apaga
  ``govbr_access_token_exp`` da sessão (senão rechamaria o IdP a cada request).
- ``load_logged_in_user`` aplica o teto absoluto de ``PERMANENT_SESSION_LIFETIME``
  sobre ``session["login_at"]``, respondendo 401 JSON em ``/api/*`` e, nas demais
  rotas, redirect ao login com ``next`` (só em GET) e flash de aviso. Se a sessão
  expulsa era Gov.br, o cookie ``govbr_refresh_token`` é apagado no after_request.
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import app as app_module
import routes.auth as auth_routes
from flask import session as flask_session
from models import User, db
from services.govbr_oidc import GovBrOIDCError


class _IdpRefreshQueFalha:
    """Substitui ``refresh_access_token`` simulando IdP recusando o refresh."""

    def __init__(self) -> None:
        self.chamadas = 0

    def __call__(self, _config, *, refresh_token: str) -> dict[str, str]:
        self.chamadas += 1
        raise GovBrOIDCError("refresh recusado pelo IdP")


class _IdpRefreshSemExpiresIn:
    """Refresh bem-sucedido, mas sem ``expires_in`` no payload."""

    def __init__(self) -> None:
        self.chamadas = 0

    def __call__(self, _config, *, refresh_token: str) -> dict[str, str]:
        self.chamadas += 1
        return {"access_token": "novo-access-token"}


def _logar_govbr_com_token_vencido(client, user_id: int) -> None:
    with client.session_transaction() as sessao:
        sessao["user_id"] = user_id
        sessao["login_at"] = time.time()
        sessao["auth_provider"] = "govbr"
        sessao["govbr_access_token_exp"] = time.time() - 60


def test_token_govbr_vencido_sem_refresh_token_mantem_sessao(client, seed_data):
    _logar_govbr_com_token_vencido(client, seed_data["user_id"])

    resposta = client.get("/api/me")

    assert resposta.status_code == 200
    with client.session_transaction() as sessao:
        assert sessao["user_id"] == seed_data["user_id"]
        assert "govbr_access_token_exp" not in sessao


def test_falha_de_refresh_govbr_nao_desloga_e_para_de_tentar(
    client, seed_data, monkeypatch
):
    idp = _IdpRefreshQueFalha()
    monkeypatch.setattr(app_module, "refresh_access_token", idp)
    client.set_cookie("govbr_refresh_token", "refresh-token-1")
    _logar_govbr_com_token_vencido(client, seed_data["user_id"])

    primeira = client.get("/api/me")
    segunda = client.get("/api/me")

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert idp.chamadas == 1
    with client.session_transaction() as sessao:
        assert sessao["user_id"] == seed_data["user_id"]
        assert "govbr_access_token_exp" not in sessao


def test_refresh_govbr_sem_expires_in_nao_entra_em_loop(client, seed_data, monkeypatch):
    idp = _IdpRefreshSemExpiresIn()
    monkeypatch.setattr(app_module, "refresh_access_token", idp)
    client.set_cookie("govbr_refresh_token", "refresh-token-2")
    _logar_govbr_com_token_vencido(client, seed_data["user_id"])

    primeira = client.get("/api/me")
    segunda = client.get("/api/me")

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert idp.chamadas == 1
    with client.session_transaction() as sessao:
        assert sessao["user_id"] == seed_data["user_id"]
        assert "govbr_access_token_exp" not in sessao


def test_teto_absoluto_responde_401_json_na_api(app, client, seed_data):
    with client.session_transaction() as sessao:
        sessao["user_id"] = seed_data["user_id"]
        sessao["login_at"] = (
            time.time() - app.permanent_session_lifetime.total_seconds() - 60
        )

    resposta = client.get("/api/me")

    assert resposta.status_code == 401
    payload = resposta.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "unauthenticated"
    with client.session_transaction() as sessao:
        assert "user_id" not in sessao


def _expirar_sessao(app, client, user_id: int, provider: str | None = None) -> None:
    with client.session_transaction() as sessao:
        sessao["user_id"] = user_id
        sessao["login_at"] = (
            time.time() - app.permanent_session_lifetime.total_seconds() - 60
        )
        if provider:
            sessao["auth_provider"] = provider


def _cookies_govbr_refresh(resposta) -> list[str]:
    return [
        valor
        for valor in resposta.headers.getlist("Set-Cookie")
        if valor.startswith("govbr_refresh_token=")
    ]


def test_teto_absoluto_redireciona_pagina_para_o_login(app, client, seed_data):
    _expirar_sessao(app, client, seed_data["user_id"])

    resposta = client.get("/dashboard", follow_redirects=False)

    assert resposta.status_code == 302
    destino = urlparse(resposta.headers["Location"])
    assert destino.path == "/login"
    assert parse_qs(destino.query)["next"] == ["http://localhost/dashboard"]
    with client.session_transaction() as sessao:
        assert "user_id" not in sessao


def test_teto_absoluto_avisa_o_usuario_na_tela_de_login(app, client, seed_data):
    _expirar_sessao(app, client, seed_data["user_id"])

    resposta = client.get("/dashboard", follow_redirects=True)

    assert resposta.status_code == 200
    assert "Sessão expirada. Faça login novamente." in resposta.get_data(as_text=True)


def test_teto_absoluto_preserva_deep_link_ate_o_login(app, client, seed_data):
    _expirar_sessao(app, client, seed_data["user_id"])
    expirada = client.get("/projetos/1", follow_redirects=False)
    next_do_redirect = parse_qs(urlparse(expirada.headers["Location"]).query)["next"][0]

    resposta = client.post(
        "/login",
        data={
            "username": seed_data["user_username"],
            "password": seed_data["user_password"],
            "next": next_do_redirect,
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 302
    assert urlparse(resposta.headers["Location"]).path == "/projetos/1"


def test_teto_absoluto_em_post_nao_propaga_next(app, client, seed_data):
    _expirar_sessao(app, client, seed_data["user_id"])

    resposta = client.post("/dashboard", data={}, follow_redirects=False)

    assert resposta.status_code == 302
    destino = urlparse(resposta.headers["Location"])
    assert destino.path == "/login"
    assert "next" not in parse_qs(destino.query)


def test_teto_absoluto_govbr_apaga_refresh_cookie_na_api(app, client, seed_data):
    _expirar_sessao(app, client, seed_data["user_id"], provider="govbr")
    client.set_cookie("govbr_refresh_token", "refresh-ainda-vivo")

    resposta = client.get("/api/me")

    assert resposta.status_code == 401
    (cookie_apagado,) = _cookies_govbr_refresh(resposta)
    assert "Max-Age=0" in cookie_apagado


def test_teto_absoluto_govbr_apaga_refresh_cookie_no_redirect(app, client, seed_data):
    _expirar_sessao(app, client, seed_data["user_id"], provider="govbr")
    client.set_cookie("govbr_refresh_token", "refresh-ainda-vivo")

    resposta = client.get("/dashboard", follow_redirects=False)

    assert resposta.status_code == 302
    (cookie_apagado,) = _cookies_govbr_refresh(resposta)
    assert "Max-Age=0" in cookie_apagado


def test_teto_absoluto_local_nao_mexe_no_cookie_govbr(app, client, seed_data):
    _expirar_sessao(app, client, seed_data["user_id"])

    resposta = client.get("/api/me")

    assert resposta.status_code == 401
    assert _cookies_govbr_refresh(resposta) == []


def test_sessao_sem_login_at_conta_como_expirada(client, seed_data):
    with client.session_transaction() as sessao:
        sessao["user_id"] = seed_data["user_id"]

    resposta = client.get("/api/me")

    assert resposta.status_code == 401
    assert resposta.get_json()["error"]["code"] == "unauthenticated"


def test_login_at_recente_mantem_o_usuario_logado(app, client, seed_data):
    with client.session_transaction() as sessao:
        sessao["user_id"] = seed_data["user_id"]
        sessao["login_at"] = (
            time.time() - app.permanent_session_lifetime.total_seconds() + 300
        )

    resposta = client.get("/api/me")

    assert resposta.status_code == 200
    assert resposta.get_json()["data"]["id"] == seed_data["user_id"]


def test_remember_auth_session_marca_login_at_e_sessao_permanente(app, seed_data):
    with app.test_request_context("/login"):
        usuario = db.session.get(User, seed_data["user_id"])
        auth_routes._remember_auth_session(usuario, provider="local")

        assert flask_session.permanent is True
        assert abs(flask_session["login_at"] - time.time()) < 5
        assert flask_session["user_id"] == seed_data["user_id"]


def test_login_local_emite_cookie_de_sessao_com_expires(client, seed_data):
    resposta = client.post(
        "/login",
        data={
            "username": seed_data["user_username"],
            "password": seed_data["user_password"],
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 302
    cookie_sessao = next(
        (
            valor
            for valor in resposta.headers.getlist("Set-Cookie")
            if valor.startswith("session=")
        ),
        None,
    )
    assert cookie_sessao is not None
    assert "Expires=" in cookie_sessao
    with client.session_transaction() as sessao:
        assert abs(sessao["login_at"] - time.time()) < 5
