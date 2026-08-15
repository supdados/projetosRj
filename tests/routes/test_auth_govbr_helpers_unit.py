"""Testes unitários das auxiliares de routes/auth.py (rede de segurança sprint 6).

Fixam o comportamento ATUAL de resolução de redirect_uri, montagem de config,
sessão pós-login (fixation), lockout e rate-key ANTES das fases 6.2-6.4 —
qualquer mudança de contrato nessas fases deve atualizar estes testes junto.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask
from flask import session as flask_session

import routes.auth as auth_routes
from models import User, db
from time_utils import utc_now

# ---------------------------------------------------------------------------
# _resolve_runtime_govbr_redirect_uri
# ---------------------------------------------------------------------------


def test_resolve_redirect_uri_sem_config_retorna_none(app: Flask) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "   "
    with app.test_request_context("/login/govbr"):
        assert auth_routes._resolve_runtime_govbr_redirect_uri() is None


def test_resolve_redirect_uri_relativo_usa_url_for_externo(app: Flask) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "/auth/govbr/callback"
    with app.test_request_context("/login/govbr", base_url="http://localhost"):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "http://localhost/auth/govbr/callback"


def test_resolve_redirect_uri_hostname_e_scheme_iguais_preserva_config(
    app: Flask,
) -> None:
    # Comparação é por hostname (sem porta): porta divergente NÃO reescreve a URI.
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "http://localhost:5002/auth/govbr/callback"
    with app.test_request_context("/login/govbr", base_url="http://localhost:8080"):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "http://localhost:5002/auth/govbr/callback"


def test_resolve_redirect_uri_host_divergente_troca_scheme_e_netloc(
    app: Flask,
) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "http://localhost:5002/auth/govbr/callback"
    with app.test_request_context("/login/govbr", base_url="http://127.0.0.1:8080"):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "http://127.0.0.1:8080/auth/govbr/callback"


def test_resolve_redirect_uri_scheme_divergente_adota_o_da_requisicao(
    app: Flask,
) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "https://app.rj.gov.br/auth/govbr/callback"
    with app.test_request_context("/login/govbr", base_url="http://app.rj.gov.br"):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "http://app.rj.gov.br/auth/govbr/callback"


def test_resolve_redirect_uri_ignora_headers_de_proxy_sem_proxyfix(app: Flask) -> None:
    # Sem ProxyFix no app, X-Forwarded-* não altera request.scheme/host.
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "http://localhost:5002/auth/govbr/callback"
    with app.test_request_context(
        "/login/govbr",
        base_url="http://localhost:5002",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "publico.rj.gov.br",
        },
    ):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "http://localhost:5002/auth/govbr/callback"


# ---------------------------------------------------------------------------
# GOVBR_OIDC_REDIRECT_URI_FIXED (config explícita por ambiente — 6.4)
# ---------------------------------------------------------------------------


def test_redirect_uri_fixa_vence_a_derivacao_por_request(app: Flask) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "http://localhost:5002/auth/govbr/callback"
    app.config["GOVBR_OIDC_REDIRECT_URI_FIXED"] = (
        "https://app.rj.gov.br/auth/govbr/callback"
    )
    with app.test_request_context("/login/govbr", base_url="http://127.0.0.1:8080"):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "https://app.rj.gov.br/auth/govbr/callback"


def test_redirect_uri_fixa_ignora_headers_de_proxy(app: Flask) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI_FIXED"] = (
        "https://app.rj.gov.br/auth/govbr/callback"
    )
    with app.test_request_context(
        "/login/govbr",
        base_url="http://localhost:5002",
        headers={"X-Forwarded-Host": "atacante.example.com"},
    ):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "https://app.rj.gov.br/auth/govbr/callback"


def test_redirect_uri_fixa_em_branco_cai_na_derivacao_legada(app: Flask) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "http://localhost:5002/auth/govbr/callback"
    app.config["GOVBR_OIDC_REDIRECT_URI_FIXED"] = "   "
    with app.test_request_context("/login/govbr", base_url="http://127.0.0.1:8080"):
        resolved = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolved == "http://127.0.0.1:8080/auth/govbr/callback"


def test_redirect_uri_fixa_ausente_nao_muda_nada_em_dev_local(app: Flask) -> None:
    # Cenário "produção sem a env nova": valor tem de ser byte-idêntico ao legado.
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "http://localhost:5002/auth/govbr/callback"
    app.config.pop("GOVBR_OIDC_REDIRECT_URI_FIXED", None)
    with app.test_request_context("/login/govbr", base_url="http://localhost:5002"):
        derivado = auth_routes._derive_govbr_redirect_uri_from_request()
        resolvido = auth_routes._resolve_runtime_govbr_redirect_uri()
    assert resolvido == derivado == "http://localhost:5002/auth/govbr/callback"


# ---------------------------------------------------------------------------
# _build_config_with_redirect_uri
# ---------------------------------------------------------------------------


def test_build_config_sem_redirect_devolve_o_config_do_app(app: Flask) -> None:
    with app.test_request_context("/"):
        assert auth_routes._build_config_with_redirect_uri(None) is app.config
        assert auth_routes._build_config_with_redirect_uri("") is app.config


def test_build_config_com_redirect_copia_e_sobrescreve(app: Flask) -> None:
    app.config["GOVBR_OIDC_REDIRECT_URI"] = "http://original/cb"
    with app.test_request_context("/"):
        config = auth_routes._build_config_with_redirect_uri("http://runtime/cb")

    assert config is not app.config
    assert config["GOVBR_OIDC_REDIRECT_URI"] == "http://runtime/cb"
    assert app.config["GOVBR_OIDC_REDIRECT_URI"] == "http://original/cb"


# ---------------------------------------------------------------------------
# _remember_auth_session (session fixation)
# ---------------------------------------------------------------------------


class UsuarioAutenticadoFake:
    """Duck-type mínimo de User para _remember_auth_session (só usa .id)."""

    def __init__(self, user_id: int) -> None:
        self.id = user_id


def test_remember_auth_session_limpa_sessao_anterior_e_rotaciona(app: Flask) -> None:
    with app.test_request_context("/login"):
        flask_session["user_id"] = 999
        flask_session["residuo_pre_login"] = "x"

        auth_routes._remember_auth_session(UsuarioAutenticadoFake(42), provider="local")

        assert "residuo_pre_login" not in flask_session
        assert flask_session["user_id"] == 42
        assert flask_session["auth_provider"] == "local"
        assert flask_session.permanent is True
        assert flask_session["_sid_rotation"]
        assert "govbr_id_token" not in flask_session


def test_remember_auth_session_guarda_id_token_apenas_para_govbr(app: Flask) -> None:
    with app.test_request_context("/login"):
        auth_routes._remember_auth_session(
            UsuarioAutenticadoFake(7), provider="govbr", id_token="id-token-7"
        )
        assert flask_session["govbr_id_token"] == "id-token-7"

    with app.test_request_context("/login"):
        auth_routes._remember_auth_session(UsuarioAutenticadoFake(7), provider="govbr")
        assert "govbr_id_token" not in flask_session


def test_remember_auth_session_gera_rotacao_diferente_a_cada_login(app: Flask) -> None:
    with app.test_request_context("/login"):
        auth_routes._remember_auth_session(UsuarioAutenticadoFake(1), provider="local")
        primeira = flask_session["_sid_rotation"]
        auth_routes._remember_auth_session(UsuarioAutenticadoFake(1), provider="local")
        segunda = flask_session["_sid_rotation"]

    assert primeira != segunda


# ---------------------------------------------------------------------------
# Lockout: _user_is_locked_out / _register_failed_login / _register_successful_login
# ---------------------------------------------------------------------------


class UsuarioComLockoutFake:
    """Duck-type mínimo para _user_is_locked_out (só usa .lockout_until)."""

    def __init__(self, lockout_until: datetime | None) -> None:
        self.lockout_until = lockout_until


def test_user_is_locked_out_cobre_ausencia_passado_e_futuro() -> None:
    assert auth_routes._user_is_locked_out(None) is False
    assert auth_routes._user_is_locked_out(UsuarioComLockoutFake(None)) is False
    passado = utc_now() - timedelta(minutes=1)
    assert auth_routes._user_is_locked_out(UsuarioComLockoutFake(passado)) is False
    futuro = utc_now() + timedelta(minutes=1)
    assert auth_routes._user_is_locked_out(UsuarioComLockoutFake(futuro)) is True


def _criar_usuario_para_lockout(username: str) -> User:
    user = User(username=username, name="Alvo Lockout", orgao="SETD")
    user.set_password("senha123")
    db.session.add(user)
    db.session.commit()
    return user


def _como_utc(value: datetime) -> datetime:
    # SQLite devolve datetime naive; normaliza para comparar com utc_now().
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def test_register_failed_login_incrementa_sem_travar_antes_do_limite(
    app: Flask,
) -> None:
    with app.test_request_context("/login"):
        user = _criar_usuario_para_lockout("alvo-quatro-falhas")
        for _ in range(auth_routes.LOCAL_LOGIN_MAX_ATTEMPTS - 1):
            auth_routes._register_failed_login(user)

        assert user.failed_login_attempts == auth_routes.LOCAL_LOGIN_MAX_ATTEMPTS - 1
        assert user.lockout_until is None


def test_register_failed_login_trava_na_quinta_tentativa_e_zera_contador(
    app: Flask,
) -> None:
    with app.test_request_context("/login"):
        user = _criar_usuario_para_lockout("alvo-cinco-falhas")
        for _ in range(auth_routes.LOCAL_LOGIN_MAX_ATTEMPTS):
            auth_routes._register_failed_login(user)

        assert user.failed_login_attempts == 0
        assert user.lockout_until is not None
        limite = _como_utc(user.lockout_until)
        esperado = _como_utc(utc_now()) + timedelta(
            minutes=auth_routes.LOCAL_LOGIN_LOCKOUT_MINUTES
        )
        assert abs((limite - esperado).total_seconds()) < 10


def test_register_failed_login_com_none_e_no_op(app: Flask) -> None:
    with app.test_request_context("/login"):
        auth_routes._register_failed_login(None)


def test_register_successful_login_zera_contadores_e_lockout(app: Flask) -> None:
    with app.test_request_context("/login"):
        user = _criar_usuario_para_lockout("alvo-sucesso")
        user.failed_login_attempts = 3
        user.lockout_until = utc_now() + timedelta(minutes=5)
        db.session.commit()

        auth_routes._register_successful_login(user)

        assert user.failed_login_attempts == 0
        assert user.lockout_until is None


def test_register_successful_login_com_none_e_no_op(app: Flask) -> None:
    with app.test_request_context("/login"):
        auth_routes._register_successful_login(None)


# ---------------------------------------------------------------------------
# _login_rate_key / _login_redirect_target
# ---------------------------------------------------------------------------


def test_login_rate_key_normaliza_username_e_prefixa_ip(app: Flask) -> None:
    with app.test_request_context(
        "/login",
        method="POST",
        data={"username": "  Admin "},
        environ_base={"REMOTE_ADDR": "10.1.2.3"},
    ):
        assert auth_routes._login_rate_key() == "10.1.2.3|admin"


def test_login_rate_key_sem_username_usa_balde_vazio(app: Flask) -> None:
    with app.test_request_context(
        "/login", method="POST", environ_base={"REMOTE_ADDR": "10.1.2.3"}
    ):
        assert auth_routes._login_rate_key() == "10.1.2.3|"


def test_login_redirect_target_aceita_next_interno(app: Flask) -> None:
    with app.test_request_context("/login", method="POST", data={"next": "/projetos"}):
        assert auth_routes._login_redirect_target() == "/projetos"


def test_login_redirect_target_rejeita_next_externo(app: Flask) -> None:
    with app.test_request_context(
        "/login", method="POST", data={"next": "https://evil.example.com/"}
    ):
        assert auth_routes._login_redirect_target() == "/dashboard"


def test_login_redirect_target_sem_next_cai_no_dashboard(app: Flask) -> None:
    with app.test_request_context("/login", method="POST"):
        assert auth_routes._login_redirect_target() == "/dashboard"
