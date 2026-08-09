import time

import routes.auth as auth_routes
from models import User, db


def _enable_govbr(app):
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


def test_login_govbr_redirects_to_provider_and_stores_state(app, client, monkeypatch):
    _enable_govbr(app)

    captured = {}

    def fake_build_authorization_url(_config, *, state, nonce):
        captured["state"] = state
        captured["nonce"] = nonce
        return "https://idp.dev/auth"

    monkeypatch.setattr(
        auth_routes, "build_authorization_url", fake_build_authorization_url
    )

    response = client.get("/login/govbr?next=/projects", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://idp.dev/auth"
    assert captured["state"]
    assert captured["nonce"]

    with client.session_transaction() as session:
        assert session["govbr_auth_state"] == captured["state"]
        assert session["govbr_auth_nonce"] == captured["nonce"]
        assert session["govbr_auth_next"] == "/projects"


def test_login_govbr_uses_request_host_for_redirect_uri_when_hostname_differs(
    app, client, monkeypatch
):
    _enable_govbr(app)

    captured = {}

    def fake_build_authorization_url(config, *, state, nonce):
        captured["redirect_uri"] = config.get("GOVBR_OIDC_REDIRECT_URI")
        return "https://idp.dev/auth"

    monkeypatch.setattr(
        auth_routes, "build_authorization_url", fake_build_authorization_url
    )

    response = client.get(
        "/login/govbr", base_url="http://127.0.0.1:5002", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "https://idp.dev/auth"
    assert captured["redirect_uri"] == "http://127.0.0.1:5002/auth/govbr/callback"


def test_login_govbr_callback_rejects_invalid_state(app, client):
    _enable_govbr(app)

    with client.session_transaction() as session:
        session["govbr_auth_state"] = "expected-state"
        session["govbr_auth_nonce"] = "expected-nonce"
        session["govbr_auth_next"] = "/projects"

    response = client.get(
        "/auth/govbr/callback?code=abc&state=other-state", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_login_govbr_callback_uses_redirect_uri_saved_in_session(
    app, client, seed_data, monkeypatch
):
    _enable_govbr(app)

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = "12345678901"
        user.govbr_sub = None
        db.session.commit()

    captured = {}

    def fake_exchange_code_for_tokens(config, *, code):
        captured["redirect_uri"] = config.get("GOVBR_OIDC_REDIRECT_URI")
        return {"access_token": f"access-{code}", "id_token": "id-token"}

    monkeypatch.setattr(
        auth_routes, "exchange_code_for_tokens", fake_exchange_code_for_tokens
    )
    monkeypatch.setattr(
        auth_routes,
        "decode_jwt_payload",
        lambda _token, **kw: {
            "nonce": "nonce-redirect",
            "preferred_username": "12345678901",
            "sub": "sub-redirect",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "fetch_userinfo",
        lambda _config, *, access_token: {
            "preferred_username": "12345678901",
            "sub": "sub-redirect",
        },
    )

    with client.session_transaction() as session:
        session["govbr_auth_state"] = "state-redirect"
        session["govbr_auth_nonce"] = "nonce-redirect"
        session["govbr_auth_redirect_uri"] = "http://127.0.0.1:5002/auth/govbr/callback"

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-redirect", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert captured["redirect_uri"] == "http://127.0.0.1:5002/auth/govbr/callback"


def test_login_govbr_callback_success_with_user_mapped_by_cpf(
    app, client, seed_data, monkeypatch
):
    _enable_govbr(app)

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = "12345678901"
        user.govbr_sub = None
        db.session.commit()

    monkeypatch.setattr(
        auth_routes,
        "exchange_code_for_tokens",
        lambda _config, *, code: {
            "access_token": f"access-{code}",
            "id_token": "id-token",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "decode_jwt_payload",
        lambda _token, **kw: {
            "nonce": "nonce-1",
            "preferred_username": "12345678901",
            "sub": "sub-1",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "fetch_userinfo",
        lambda _config, *, access_token: {
            "preferred_username": "12345678901",
            "sub": "sub-1",
        },
    )

    with client.session_transaction() as session:
        session["govbr_auth_state"] = "state-1"
        session["govbr_auth_nonce"] = "nonce-1"
        session["govbr_auth_next"] = "/projects"

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-1", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/projects")

    with client.session_transaction() as session:
        assert session["user_id"] == seed_data["user_id"]
        assert session["auth_provider"] == "govbr"
        assert session["govbr_id_token"] == "id-token"

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user is not None
        assert user.govbr_sub == "sub-1"


def test_login_govbr_callback_fallback_by_username_sets_cpf(app, client, monkeypatch):
    _enable_govbr(app)

    with app.app_context():
        user = User(
            username="123.456.789-01",
            name="Usuario GovBr",
            orgao="Orgao Teste",
            is_admin=False,
        )
        user.set_password("senha123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    monkeypatch.setattr(
        auth_routes,
        "exchange_code_for_tokens",
        lambda _config, *, code: {
            "access_token": f"access-{code}",
            "id_token": "id-token",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "decode_jwt_payload",
        lambda _token, **kw: {
            "nonce": "nonce-2",
            "preferred_username": "12345678901",
            "sub": "sub-2",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "fetch_userinfo",
        lambda _config, *, access_token: {
            "preferred_username": "12345678901",
            "sub": "sub-2",
        },
    )

    with client.session_transaction() as session:
        session["govbr_auth_state"] = "state-2"
        session["govbr_auth_nonce"] = "nonce-2"

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-2", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        assert user.cpf_govbr == "12345678901"
        assert user.govbr_sub == "sub-2"


def test_login_govbr_callback_blocks_when_user_is_not_linked(app, client, monkeypatch):
    _enable_govbr(app)

    monkeypatch.setattr(
        auth_routes,
        "exchange_code_for_tokens",
        lambda _config, *, code: {
            "access_token": f"access-{code}",
            "id_token": "id-token",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "decode_jwt_payload",
        lambda _token, **kw: {
            "nonce": "nonce-3",
            "preferred_username": "11122233344",
            "sub": "sub-3",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "fetch_userinfo",
        lambda _config, *, access_token: {
            "preferred_username": "11122233344",
            "sub": "sub-3",
        },
    )

    with client.session_transaction() as session:
        session["govbr_auth_state"] = "state-3"
        session["govbr_auth_nonce"] = "nonce-3"

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-3", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_login_govbr_callback_blocks_when_sub_conflicts(
    app, client, seed_data, monkeypatch
):
    _enable_govbr(app)

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = "12345678901"
        user.govbr_sub = "sub-old"
        db.session.commit()

    monkeypatch.setattr(
        auth_routes,
        "exchange_code_for_tokens",
        lambda _config, *, code: {
            "access_token": f"access-{code}",
            "id_token": "id-token",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "decode_jwt_payload",
        lambda _token, **kw: {
            "nonce": "nonce-4",
            "preferred_username": "12345678901",
            "sub": "sub-new",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "fetch_userinfo",
        lambda _config, *, access_token: {
            "preferred_username": "12345678901",
            "sub": "sub-new",
        },
    )

    with client.session_transaction() as session:
        session["govbr_auth_state"] = "state-4"
        session["govbr_auth_nonce"] = "nonce-4"

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-4", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_login_govbr_callback_prefers_existing_sub_without_needing_cpf(
    app, client, seed_data, monkeypatch
):
    _enable_govbr(app)

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = None
        user.govbr_sub = "sub-principal"
        db.session.commit()

    monkeypatch.setattr(
        auth_routes,
        "exchange_code_for_tokens",
        lambda _config, *, code: {
            "access_token": f"access-{code}",
            "id_token": "id-token",
        },
    )
    monkeypatch.setattr(
        auth_routes,
        "decode_jwt_payload",
        lambda _token, **kw: {"nonce": "nonce-5", "sub": "sub-principal"},
    )
    monkeypatch.setattr(
        auth_routes,
        "fetch_userinfo",
        lambda _config, *, access_token: {"sub": "sub-principal"},
    )

    with client.session_transaction() as session:
        session["govbr_auth_state"] = "state-5"
        session["govbr_auth_nonce"] = "nonce-5"

    response = client.get(
        "/auth/govbr/callback?code=ok&state=state-5", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    with client.session_transaction() as session:
        assert session["user_id"] == seed_data["user_id"]
        assert session["auth_provider"] == "govbr"


def test_logout_for_govbr_session_defaults_to_local_login_redirect(
    app, client, seed_data, monkeypatch
):
    _enable_govbr(app)
    monkeypatch.setattr(
        auth_routes,
        "build_logout_url",
        lambda _config, *, id_token_hint, post_logout_redirect_uri: "https://idp.dev/logout",
    )

    with client.session_transaction() as session:
        session["user_id"] = seed_data["user_id"]
        session["login_at"] = time.time()
        session["auth_provider"] = "govbr"
        session["govbr_id_token"] = "id-token"

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_logout_for_govbr_session_redirects_to_federated_when_enabled(
    app, client, seed_data, monkeypatch
):
    _enable_govbr(app)
    app.config["GOVBR_OIDC_FEDERATED_LOGOUT_ENABLED"] = True
    monkeypatch.setattr(
        auth_routes,
        "build_logout_url",
        lambda _config, *, id_token_hint, post_logout_redirect_uri: "https://idp.dev/logout",
    )

    with client.session_transaction() as session:
        session["user_id"] = seed_data["user_id"]
        session["login_at"] = time.time()
        session["auth_provider"] = "govbr"
        session["govbr_id_token"] = "id-token"

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://idp.dev/logout"


def test_logout_for_local_session_keeps_regular_redirect(
    app, client, seed_data, monkeypatch
):
    _enable_govbr(app)
    monkeypatch.setattr(
        auth_routes,
        "build_logout_url",
        lambda _config, *, id_token_hint, post_logout_redirect_uri: "https://idp.dev/logout",
    )

    with client.session_transaction() as session:
        session["user_id"] = seed_data["user_id"]
        session["login_at"] = time.time()
        session["auth_provider"] = "local"

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
