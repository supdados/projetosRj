"""Contrato ATUAL do callback Gov.br (rede sprint 6).

A partir da 6.3 o par verificado manda: sub vem SEMPRE do id_token validado
(userinfo só complementa claims e diverge → bloqueio) e nonce enviado na
authorize é obrigatório no id_token. A partir da 6.2 fixa também o contrato
NEGATIVO do refresh: o callback não emite cookie ``govbr_refresh_token`` nem
grava expiração de token na sessão.
"""

from __future__ import annotations

import time
from typing import Any

from flask import Flask
from flask.testing import FlaskClient

import routes.auth as auth_routes
from models import User, db

TOKENS_OK: dict[str, Any] = {"access_token": "access-1", "id_token": "id-token-1"}


def _enable_govbr(app: Flask) -> None:
    app.config.update(
        GOVBR_OIDC_ENABLED=True,
        GOVBR_OIDC_BASE_URL="https://secretarias.idp.dev.proderj.rj.gov.br",
        GOVBR_OIDC_REALM="rj",
        GOVBR_OIDC_CLIENT_ID="setd-projetosrj",
        GOVBR_OIDC_CLIENT_SECRET="secret-test",
        GOVBR_OIDC_REDIRECT_URI="http://localhost:5002/auth/govbr/callback",
        GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI="http://localhost:5002/login",
        GOVBR_OIDC_FEDERATED_LOGOUT_ENABLED=False,
        GOVBR_OIDC_SCOPE="openid profile email",
        GOVBR_OIDC_TIMEOUT_SECONDS=10,
    )


class TrocadorDeCodigoFake:
    """Substitui exchange_code_for_tokens sem sair para o IdP real."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)
        self.redirect_uris: list[str | None] = []

    def __call__(self, config: dict[str, Any], *, code: str) -> dict[str, Any]:
        self.redirect_uris.append(config.get("GOVBR_OIDC_REDIRECT_URI"))
        return dict(self._payload)


class DecodificadorIdTokenFake:
    """Substitui decode_jwt_payload capturando os kwargs usados no callback."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)
        self.kwargs_vistos: list[dict[str, Any]] = []

    def __call__(self, token: str, **kwargs: Any) -> dict[str, Any]:
        self.kwargs_vistos.append(kwargs)
        return dict(self._payload)


class UserinfoFake:
    """Substitui fetch_userinfo devolvendo claims fixos."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)

    def __call__(self, config: dict[str, Any], *, access_token: str) -> dict[str, Any]:
        return dict(self._payload)


def _instalar_idp_fake(
    monkeypatch: Any,
    *,
    tokens: dict[str, Any],
    id_payload: dict[str, Any],
    userinfo: dict[str, Any],
) -> tuple[TrocadorDeCodigoFake, DecodificadorIdTokenFake, UserinfoFake]:
    trocador = TrocadorDeCodigoFake(tokens)
    decodificador = DecodificadorIdTokenFake(id_payload)
    fetcher = UserinfoFake(userinfo)
    monkeypatch.setattr(auth_routes, "exchange_code_for_tokens", trocador)
    monkeypatch.setattr(auth_routes, "decode_jwt_payload", decodificador)
    monkeypatch.setattr(auth_routes, "fetch_userinfo", fetcher)
    return trocador, decodificador, fetcher


def _preparar_sessao(
    client: FlaskClient, *, state: str = "state-x", nonce: str = "nonce-x", **extra: str
) -> None:
    with client.session_transaction() as session:
        session["govbr_auth_state"] = state
        session["govbr_auth_nonce"] = nonce
        for chave, valor in extra.items():
            session[chave] = valor


def _criar_usuario_govbr(
    app: Flask, *, username: str, cpf: str | None = None, sub: str | None = None
) -> int:
    with app.app_context():
        user = User(username=username, name=f"Usuario {username}", orgao="SETD")
        user.set_password("senha123")
        user.cpf_govbr = cpf
        user.govbr_sub = sub
        db.session.add(user)
        db.session.commit()
        return user.id


def _sessao_user_id(client: FlaskClient) -> int | None:
    with client.session_transaction() as session:
        return session.get("user_id")


# ---------------------------------------------------------------------------
# Claims: CPF ainda prefere userinfo; sub é exclusivo do id_token verificado
# ---------------------------------------------------------------------------


def test_callback_prefere_cpf_do_userinfo_sobre_id_token(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    id_do_userinfo = _criar_usuario_govbr(app, username="u-userinfo", cpf="11111111111")
    _criar_usuario_govbr(app, username="u-idtoken", cpf="22222222222")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "22222222222",
            "sub": "sub-prec",
        },
        userinfo={"preferred_username": "11111111111", "sub": "sub-prec"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert _sessao_user_id(client) == id_do_userinfo


def test_callback_usa_cpf_do_id_token_quando_userinfo_nao_traz(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    user_id = _criar_usuario_govbr(app, username="u-fallback", cpf="33333333333")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "33333333333",
            "sub": "sub-fb",
        },
        userinfo={"sub": "sub-fb"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert _sessao_user_id(client) == user_id


def test_callback_sem_sub_em_nenhuma_fonte_bloqueia(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    _criar_usuario_govbr(app, username="u-sem-sub", cpf="44444444444")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={"nonce": "nonce-x", "preferred_username": "44444444444"},
        userinfo={"preferred_username": "44444444444"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert _sessao_user_id(client) is None


def test_callback_sub_apenas_no_userinfo_bloqueia(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    """O 'or' morreu: sub do userinfo não substitui sub ausente no id_token."""
    _enable_govbr(app)
    _criar_usuario_govbr(app, username="u-sub-userinfo", cpf="12312312312")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={"nonce": "nonce-x", "preferred_username": "12312312312"},
        userinfo={"preferred_username": "12312312312", "sub": "sub-so-userinfo"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert _sessao_user_id(client) is None


def test_callback_sub_divergente_entre_userinfo_e_id_token_bloqueia(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    """Cross-check OIDC: userinfo.sub != id_token.sub aborta o login."""
    _enable_govbr(app)
    _criar_usuario_govbr(app, username="u-divergente", cpf="32132132132")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "32132132132",
            "sub": "sub-id-token",
        },
        userinfo={"preferred_username": "32132132132", "sub": "sub-atacante"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert _sessao_user_id(client) is None


def test_callback_userinfo_sem_sub_usa_id_token_verificado(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    """Sem sub no userinfo o id_token verificado segue como fonte primária."""
    _enable_govbr(app)
    user_id = _criar_usuario_govbr(app, username="u-primario", cpf="45645645645")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "45645645645",
            "sub": "sub-primario",
        },
        userinfo={"preferred_username": "45645645645"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert _sessao_user_id(client) == user_id
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        assert user.govbr_sub == "sub-primario"


# ---------------------------------------------------------------------------
# Ramos de erro do callback
# ---------------------------------------------------------------------------


def test_callback_com_error_do_provedor_redireciona_e_consome_state(
    app: Flask, client: FlaskClient
) -> None:
    _enable_govbr(app)
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?error=access_denied", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as session:
        assert "govbr_auth_state" not in session
        assert "govbr_auth_nonce" not in session


def test_callback_sem_code_ou_sem_state_redireciona(
    app: Flask, client: FlaskClient
) -> None:
    _enable_govbr(app)
    for query in ("?state=state-x", "?code=ok"):
        _preparar_sessao(client)
        response = client.get(f"/auth/govbr/callback{query}", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")


def test_callback_sem_sessao_de_estado_redireciona(
    app: Flask, client: FlaskClient
) -> None:
    _enable_govbr(app)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=qualquer", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_callback_nonce_divergente_bloqueia(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    _criar_usuario_govbr(app, username="u-nonce", cpf="55555555555")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-forjado",
            "preferred_username": "55555555555",
            "sub": "sub-nonce",
        },
        userinfo={"preferred_username": "55555555555", "sub": "sub-nonce"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert _sessao_user_id(client) is None


def test_callback_nonce_ausente_no_id_token_bloqueia(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    """6.3: nonce enviado na authorize é obrigatório no id_token — sem tolerância."""
    _enable_govbr(app)
    _criar_usuario_govbr(app, username="u-sem-nonce", cpf="66666666666")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={"preferred_username": "66666666666", "sub": "sub-sem-nonce"},
        userinfo={"preferred_username": "66666666666", "sub": "sub-sem-nonce"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert _sessao_user_id(client) is None


def test_callback_nonce_valido_no_id_token_passa(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    user_id = _criar_usuario_govbr(app, username="u-nonce-ok", cpf="67676767676")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "67676767676",
            "sub": "sub-nonce-ok",
        },
        userinfo={"preferred_username": "67676767676", "sub": "sub-nonce-ok"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert _sessao_user_id(client) == user_id


def test_callback_resposta_de_token_incompleta_redireciona(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    for tokens in ({"access_token": "a"}, {"id_token": "b"}):
        _instalar_idp_fake(
            monkeypatch, tokens=tokens, id_payload={}, userinfo={"sub": "s"}
        )
        _preparar_sessao(client)
        response = client.get(
            "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert _sessao_user_id(client) is None


def test_callback_cpf_invalido_impede_vinculo_inicial(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "nao-e-cpf",
            "sub": "sub-cpf-ruim",
        },
        userinfo={"preferred_username": "nao-e-cpf", "sub": "sub-cpf-ruim"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert _sessao_user_id(client) is None


# ---------------------------------------------------------------------------
# Decode do id_token com config (6.3) e backfill de CPF por sub
# ---------------------------------------------------------------------------


def test_callback_decodifica_id_token_com_config_da_sessao(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    _criar_usuario_govbr(app, username="u-config", cpf="77777777777")
    trocador, decodificador, _ = _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "77777777777",
            "sub": "sub-config",
        },
        userinfo={"preferred_username": "77777777777", "sub": "sub-config"},
    )
    _preparar_sessao(
        client,
        govbr_auth_redirect_uri="http://127.0.0.1:5002/auth/govbr/callback",
    )

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    config_do_decode = decodificador.kwargs_vistos[0]["config"]
    assert (
        config_do_decode["GOVBR_OIDC_REDIRECT_URI"]
        == "http://127.0.0.1:5002/auth/govbr/callback"
    )
    assert trocador.redirect_uris == ["http://127.0.0.1:5002/auth/govbr/callback"]


def test_callback_backfilla_cpf_de_usuario_ja_vinculado_por_sub(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    _enable_govbr(app)
    user_id = _criar_usuario_govbr(app, username="u-backfill", sub="sub-backfill")
    _instalar_idp_fake(
        monkeypatch,
        tokens=TOKENS_OK,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": "88888888888",
            "sub": "sub-backfill",
        },
        userinfo={"preferred_username": "88888888888", "sub": "sub-backfill"},
    )
    _preparar_sessao(client)

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )

    assert response.status_code == 302
    assert _sessao_user_id(client) == user_id
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        assert user.cpf_govbr == "88888888888"


# ---------------------------------------------------------------------------
# 6.2: o refresh Gov.br morreu — nada de cookie nem de chaves de sessão
# ---------------------------------------------------------------------------

TOKENS_COM_REFRESH: dict[str, Any] = {
    **TOKENS_OK,
    "expires_in": 300,
    "refresh_token": "rt-1",
    "refresh_expires_in": 1800,
}


def _cookies_govbr_refresh(response: Any) -> list[str]:
    return [
        valor
        for valor in response.headers.getlist("Set-Cookie")
        if valor.startswith("govbr_refresh_token=")
    ]


def _login_govbr_com_tokens(
    app: Flask,
    client: FlaskClient,
    monkeypatch: Any,
    *,
    username: str,
    cpf: str,
    tokens: dict[str, Any],
) -> Any:
    _enable_govbr(app)
    _criar_usuario_govbr(app, username=username, cpf=cpf)
    _instalar_idp_fake(
        monkeypatch,
        tokens=tokens,
        id_payload={
            "nonce": "nonce-x",
            "preferred_username": cpf,
            "sub": f"sub-{username}",
        },
        userinfo={"preferred_username": cpf, "sub": f"sub-{username}"},
    )
    _preparar_sessao(client)
    return client.get(
        "/auth/govbr/callback?code=ok&state=state-x", follow_redirects=False
    )


def test_callback_nao_emite_cookie_de_refresh_mesmo_com_token_no_payload(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    """O refresh token do IdP é descartado: nada vai parar no navegador."""
    response = _login_govbr_com_tokens(
        app,
        client,
        monkeypatch,
        username="u-cookie",
        cpf="99999999999",
        tokens=TOKENS_COM_REFRESH,
    )

    assert response.status_code == 302
    assert _cookies_govbr_refresh(response) == []


def test_callback_nao_grava_chaves_de_expiracao_de_token_na_sessao(
    app: Flask, client: FlaskClient, monkeypatch: Any
) -> None:
    response = _login_govbr_com_tokens(
        app,
        client,
        monkeypatch,
        username="u-sem-exp",
        cpf="10101010101",
        tokens=TOKENS_COM_REFRESH,
    )

    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "govbr_access_token_exp" not in session
        assert "govbr_refresh_exp" not in session


def test_app_nao_registra_hook_de_refresh_govbr(app: Flask) -> None:
    """Nenhum before_request pode voltar a falar com o IdP no caminho da request."""
    hooks = [
        funcao.__name__
        for funcoes in app.before_request_funcs.values()
        for funcao in funcoes
    ]

    assert not any("refresh" in nome for nome in hooks)


def test_navegacao_autenticada_govbr_nao_emite_cookie_de_refresh(
    client: FlaskClient, seed_data: dict[str, Any]
) -> None:
    with client.session_transaction() as session:
        session["user_id"] = seed_data["user_id"]
        session["login_at"] = time.time()
        session["auth_provider"] = "govbr"

    response = client.get("/api/me")

    assert response.status_code == 200
    assert _cookies_govbr_refresh(response) == []


def test_logout_expira_cookie_legado_de_refresh(
    client: FlaskClient, seed_data: dict[str, Any]
) -> None:
    # Higiene transitória: navegadores pré-sprint-6 ainda têm o cookie legado
    # com refresh token do IdP; o logout emite a expiração (Max-Age=0).
    with client.session_transaction() as session:
        session["user_id"] = seed_data["user_id"]
        session["login_at"] = time.time()
        session["auth_provider"] = "govbr"

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    cookies = _cookies_govbr_refresh(response)
    assert len(cookies) == 1
    assert "govbr_refresh_token=;" in cookies[0] or 'govbr_refresh_token="";' in cookies[0]
    assert "Max-Age=0" in cookies[0] or "Expires=Thu, 01 Jan 1970" in cookies[0]
