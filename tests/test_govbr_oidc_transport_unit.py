"""Testes unitários da camada de transporte de services/govbr_oidc.py.

Complementa test_govbr_oidc_service_unit.py fixando o que ele NÃO cobre:
URLs de autorização/logout, corpo/headers das chamadas de token/userinfo,
mapeamento de erros HTTP do IdP, normalizadores de config e os kwargs exatos do
jwt.decode verificado (audience/issuer/algoritmos — base da fase 6.3).
Nenhum teste sai para a rede: urlopen/jwt são substituídos por fakes nomeados.
"""

from __future__ import annotations

import io
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from services import govbr_oidc
from services.govbr_oidc import (
    GovBrOIDCError,
    _as_bool,
    _normalize_base_url,
    _normalize_timeout,
    build_authorization_url,
    build_logout_url,
    decode_jwt_payload,
    exchange_code_for_tokens,
    fetch_userinfo,
)


def _config_valida(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "GOVBR_OIDC_ENABLED": True,
        "GOVBR_OIDC_BASE_URL": "https://idp.example.com",
        "GOVBR_OIDC_REALM": "my-realm",
        "GOVBR_OIDC_CLIENT_ID": "my-client",
        "GOVBR_OIDC_CLIENT_SECRET": "secret",
        "GOVBR_OIDC_REDIRECT_URI": "https://app.example.com/callback",
        "GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI": "https://app.example.com/after-logout",
        "GOVBR_OIDC_SCOPE": "openid profile email",
        "GOVBR_OIDC_TIMEOUT_SECONDS": 5,
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# build_authorization_url / build_logout_url
# ---------------------------------------------------------------------------


def test_build_authorization_url_monta_todos_os_parametros() -> None:
    url = build_authorization_url(_config_valida(), state="st-1", nonce="no-1")

    parsed = urlparse(url)
    assert (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        == "https://idp.example.com/auth/realms/my-realm/protocol/openid-connect/auth"
    )
    params = parse_qs(parsed.query)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["my-client"]
    assert params["redirect_uri"] == ["https://app.example.com/callback"]
    assert params["scope"] == ["openid profile email"]
    assert params["state"] == ["st-1"]
    assert params["nonce"] == ["no-1"]


def test_build_logout_url_prefere_redirect_explicito() -> None:
    url = build_logout_url(
        _config_valida(),
        id_token_hint="idt-1",
        post_logout_redirect_uri="https://app.example.com/tchau",
    )

    params = parse_qs(urlparse(url).query)
    assert params["post_logout_redirect_uri"] == ["https://app.example.com/tchau"]
    assert params["id_token_hint"] == ["idt-1"]


def test_build_logout_url_cai_no_redirect_configurado() -> None:
    url = build_logout_url(_config_valida(), id_token_hint="idt-2")

    params = parse_qs(urlparse(url).query)
    assert params["post_logout_redirect_uri"] == [
        "https://app.example.com/after-logout"
    ]


def test_build_logout_url_sem_redirect_algum_falha() -> None:
    config = _config_valida({"GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI": ""})
    with pytest.raises(GovBrOIDCError, match="post_logout_redirect_uri"):
        build_logout_url(config, id_token_hint="idt-3")


# ---------------------------------------------------------------------------
# Transporte HTTP (urlopen substituído por fakes nomeados)
# ---------------------------------------------------------------------------


class RespostaHttpFake:
    """Context manager compatível com o retorno de urlopen."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "RespostaHttpFake":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class UrlopenComRespostaFake:
    """urlopen que devolve um corpo fixo e grava a Request recebida."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.requests: list[Any] = []
        self.timeouts: list[int | None] = []

    def __call__(self, req: Any, timeout: int | None = None) -> RespostaHttpFake:
        self.requests.append(req)
        self.timeouts.append(timeout)
        return RespostaHttpFake(self._body)


class UrlopenComErroHttpFake:
    """urlopen que simula resposta HTTP de erro do IdP (4xx/5xx)."""

    def __init__(self, code: int, body: bytes) -> None:
        self._code = code
        self._body = body

    def __call__(self, req: Any, timeout: int | None = None) -> RespostaHttpFake:
        raise HTTPError(req.full_url, self._code, "erro", None, io.BytesIO(self._body))


class UrlopenSemConectividadeFake:
    """urlopen que simula falha de rede/DNS antes de resposta HTTP."""

    def __call__(self, req: Any, timeout: int | None = None) -> RespostaHttpFake:
        raise URLError("dns indisponivel")


def test_exchange_code_for_tokens_envia_authorization_code(monkeypatch: Any) -> None:
    urlopen_fake = UrlopenComRespostaFake(json.dumps({"access_token": "at-1"}).encode())
    monkeypatch.setattr(govbr_oidc, "urlopen", urlopen_fake)

    payload = exchange_code_for_tokens(_config_valida(), code="code-1")

    assert payload == {"access_token": "at-1"}
    (req,) = urlopen_fake.requests
    assert req.full_url == (
        "https://idp.example.com/auth/realms/my-realm/protocol/openid-connect/token"
    )
    assert req.get_method() == "POST"
    assert req.headers["Content-type"] == "application/x-www-form-urlencoded"
    form = parse_qs(req.data.decode("utf-8"))
    assert form["grant_type"] == ["authorization_code"]
    assert form["client_id"] == ["my-client"]
    assert form["client_secret"] == ["secret"]
    assert form["code"] == ["code-1"]
    assert form["redirect_uri"] == ["https://app.example.com/callback"]
    assert urlopen_fake.timeouts == [5]


def test_exchange_code_for_tokens_sem_access_token_falha(monkeypatch: Any) -> None:
    urlopen_fake = UrlopenComRespostaFake(json.dumps({"id_token": "só"}).encode())
    monkeypatch.setattr(govbr_oidc, "urlopen", urlopen_fake)

    with pytest.raises(GovBrOIDCError, match="access_token"):
        exchange_code_for_tokens(_config_valida(), code="code-2")


def test_fetch_userinfo_manda_bearer_e_exige_sub(monkeypatch: Any) -> None:
    urlopen_fake = UrlopenComRespostaFake(json.dumps({"sub": "sub-1"}).encode())
    monkeypatch.setattr(govbr_oidc, "urlopen", urlopen_fake)

    payload = fetch_userinfo(_config_valida(), access_token="tok-1")

    assert payload == {"sub": "sub-1"}
    (req,) = urlopen_fake.requests
    assert req.get_method() == "GET"
    assert req.headers["Authorization"] == "Bearer tok-1"
    assert req.data is None


def test_fetch_userinfo_sem_sub_falha(monkeypatch: Any) -> None:
    urlopen_fake = UrlopenComRespostaFake(json.dumps({"name": "Fulano"}).encode())
    monkeypatch.setattr(govbr_oidc, "urlopen", urlopen_fake)

    with pytest.raises(GovBrOIDCError, match="sub"):
        fetch_userinfo(_config_valida(), access_token="tok-2")


def test_erro_http_do_idp_vira_govbroidcerror_com_codigo_e_corpo(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        govbr_oidc, "urlopen", UrlopenComErroHttpFake(400, b'{"error":"invalid_grant"}')
    )

    with pytest.raises(GovBrOIDCError, match=r"400.*invalid_grant"):
        exchange_code_for_tokens(_config_valida(), code="code-3")


def test_falha_de_conectividade_vira_govbroidcerror(monkeypatch: Any) -> None:
    monkeypatch.setattr(govbr_oidc, "urlopen", UrlopenSemConectividadeFake())

    with pytest.raises(GovBrOIDCError, match="conectividade"):
        fetch_userinfo(_config_valida(), access_token="tok-3")


def test_resposta_nao_json_do_idp_falha(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        govbr_oidc, "urlopen", UrlopenComRespostaFake(b"<html>erro</html>")
    )

    with pytest.raises(GovBrOIDCError, match="JSON"):
        exchange_code_for_tokens(_config_valida(), code="code-4")


def test_resposta_json_nao_objeto_falha(monkeypatch: Any) -> None:
    monkeypatch.setattr(govbr_oidc, "urlopen", UrlopenComRespostaFake(b"[1, 2, 3]"))

    with pytest.raises(GovBrOIDCError, match="formato"):
        exchange_code_for_tokens(_config_valida(), code="code-5")


# ---------------------------------------------------------------------------
# Normalizadores de config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "abc", 0, -5])
def test_normalize_timeout_invalido_cai_no_default(raw: Any) -> None:
    assert _normalize_timeout(raw) == 10


def test_normalize_timeout_aceita_valor_valido_mesmo_como_string() -> None:
    assert _normalize_timeout(7) == 7
    assert _normalize_timeout("7") == 7


@pytest.mark.parametrize("raw", ["1", "true", "YES", " on "])
def test_as_bool_reconhece_valores_verdadeiros(raw: str) -> None:
    assert _as_bool(raw) is True


@pytest.mark.parametrize("raw", ["0", "false", "", None, "off"])
def test_as_bool_rejeita_valores_falsos(raw: Any) -> None:
    assert _as_bool(raw) is False


def test_normalize_base_url_corta_barra_final_e_trata_vazio() -> None:
    assert _normalize_base_url("https://idp.example.com/") == "https://idp.example.com"
    assert _normalize_base_url(None) == ""
    assert _normalize_base_url("") == ""


# ---------------------------------------------------------------------------
# Kwargs do decode verificado (6.3 — único caminho de decode que existe)
# ---------------------------------------------------------------------------


class JwksClientFake:
    """PyJWKClient substituto que devolve uma chave fixa sem rede."""

    def get_signing_key_from_jwt(self, token: str) -> "ChaveDeAssinaturaFake":
        return ChaveDeAssinaturaFake()


class ChaveDeAssinaturaFake:
    key = "CHAVE_PUBLICA_FAKE"


class DecodeJwtCapturaFake:
    """Substitui jwt.decode gravando os kwargs de validação usados."""

    def __init__(self) -> None:
        self.key: Any = None
        self.kwargs: dict[str, Any] = {}

    def __call__(self, token: str, key: Any, **kwargs: Any) -> dict[str, Any]:
        self.key = key
        self.kwargs = kwargs
        return {"sub": "sub-verificado"}


def test_decode_verificado_valida_audience_issuer_e_algoritmo(
    monkeypatch: Any,
) -> None:
    captura = DecodeJwtCapturaFake()
    monkeypatch.setattr(govbr_oidc, "_get_jwks_client", lambda uri: JwksClientFake())
    monkeypatch.setattr(govbr_oidc.jwt, "decode", captura)

    payload = decode_jwt_payload("a.b.c", config=_config_valida())

    assert payload == {"sub": "sub-verificado"}
    assert captura.key == "CHAVE_PUBLICA_FAKE"
    assert captura.kwargs["algorithms"] == ["RS256"]
    assert captura.kwargs["audience"] == "my-client"
    assert captura.kwargs["issuer"] == "https://idp.example.com/auth/realms/my-realm"
    assert set(captura.kwargs["options"]["require"]) == {"exp", "iss", "aud", "sub"}
