"""Testes unitários de services.govbr_oidc.

Cobre as funções puras de normalização/formatação de CPF e o decodificador
de JWT (modo verificado x fallback). Mocka PyJWKClient/jwt.decode para não
depender de rede real."""

import base64
import json
from types import SimpleNamespace

import jwt as pyjwt
import pytest

from services import govbr_oidc
from services.govbr_oidc import (
    GovBrOIDCError,
    _decode_jwt_unverified,
    _get_jwks_client,
    decode_jwt_payload,
    format_cpf,
    normalize_cpf,
)


# ---------------------------------------------------------------------------
# normalize_cpf / format_cpf
# ---------------------------------------------------------------------------


def test_normalize_cpf_strips_formatting():
    assert normalize_cpf('123.456.789-01') == '12345678901'


def test_normalize_cpf_accepts_only_digits():
    assert normalize_cpf('12345678901') == '12345678901'


def test_normalize_cpf_returns_none_for_empty_values():
    assert normalize_cpf(None) is None
    assert normalize_cpf('') is None
    assert normalize_cpf('   ') is None


@pytest.mark.parametrize('value', ['1234567890', '123456789012', 'abc', '123.abc.789-01'])
def test_normalize_cpf_raises_when_digits_count_mismatches(value):
    with pytest.raises(ValueError):
        normalize_cpf(value)


def test_format_cpf_applies_mask():
    assert format_cpf('12345678901') == '123.456.789-01'


def test_format_cpf_returns_empty_for_none():
    assert format_cpf(None) == ''


def test_format_cpf_propagates_invalid_input():
    with pytest.raises(ValueError):
        format_cpf('123')


# ---------------------------------------------------------------------------
# decode_jwt_payload (fallback, sem config)
# ---------------------------------------------------------------------------


def _make_unsigned_jwt(payload_dict):
    header = {'alg': 'none', 'typ': 'JWT'}

    def _b64(obj):
        raw = json.dumps(obj, separators=(',', ':')).encode('utf-8')
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')

    return f"{_b64(header)}.{_b64(payload_dict)}."


def test_decode_jwt_payload_unverified_returns_payload():
    token = _make_unsigned_jwt({'sub': '123', 'email': 'a@b.com'})
    payload = decode_jwt_payload(token)

    assert payload['sub'] == '123'
    assert payload['email'] == 'a@b.com'


def test_decode_jwt_payload_rejects_malformed_token():
    with pytest.raises(GovBrOIDCError):
        decode_jwt_payload('apenas_uma_parte')


def test_decode_jwt_payload_rejects_empty_token():
    with pytest.raises(GovBrOIDCError):
        decode_jwt_payload('')


def test_decode_jwt_payload_unverified_rejects_non_json_body():
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b'=').decode('ascii')
    body = base64.urlsafe_b64encode(b'not-a-json').rstrip(b'=').decode('ascii')
    token = f'{header}.{body}.'
    with pytest.raises(GovBrOIDCError):
        _decode_jwt_unverified(token)


def test_decode_jwt_payload_unverified_rejects_non_dict_body():
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b'=').decode('ascii')
    body = base64.urlsafe_b64encode(b'[1, 2, 3]').rstrip(b'=').decode('ascii')
    token = f'{header}.{body}.'
    with pytest.raises(GovBrOIDCError):
        _decode_jwt_unverified(token)


# ---------------------------------------------------------------------------
# decode_jwt_payload (verificado, com config)
# ---------------------------------------------------------------------------


def _make_config(overrides=None):
    base = {
        'GOVBR_OIDC_ENABLED': True,
        'GOVBR_OIDC_BASE_URL': 'https://idp.example.com',
        'GOVBR_OIDC_REALM': 'my-realm',
        'GOVBR_OIDC_CLIENT_ID': 'my-client',
        'GOVBR_OIDC_CLIENT_SECRET': 'secret',
        'GOVBR_OIDC_REDIRECT_URI': 'https://app.example.com/callback',
        'GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI': 'https://app.example.com/after-logout',
        'GOVBR_OIDC_SCOPE': 'openid profile email',
        'GOVBR_OIDC_TIMEOUT_SECONDS': 5,
    }
    if overrides:
        base.update(overrides)
    return base


def _install_fake_jwks_client(monkeypatch):
    fake_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key='FAKE_PUBLIC_KEY'),
    )
    monkeypatch.setattr(govbr_oidc, '_get_jwks_client', lambda jwks_uri: fake_client)
    return fake_client


def test_decode_jwt_payload_verified_returns_payload(monkeypatch):
    config = _make_config()
    _install_fake_jwks_client(monkeypatch)

    expected = {'sub': 'abc', 'iss': 'x', 'aud': 'my-client', 'exp': 1}
    monkeypatch.setattr(govbr_oidc.jwt, 'decode', lambda *a, **kw: expected)

    assert decode_jwt_payload('a.b.c', config=config) == expected


def test_decode_jwt_payload_verified_maps_expired_signature(monkeypatch):
    config = _make_config()
    _install_fake_jwks_client(monkeypatch)

    def _fake_decode(*args, **kwargs):
        raise pyjwt.ExpiredSignatureError('expired')

    monkeypatch.setattr(govbr_oidc.jwt, 'decode', _fake_decode)

    with pytest.raises(GovBrOIDCError, match='expirado'):
        decode_jwt_payload('a.b.c', config=config)


def test_decode_jwt_payload_verified_maps_invalid_issuer(monkeypatch):
    config = _make_config()
    _install_fake_jwks_client(monkeypatch)

    def _fake_decode(*args, **kwargs):
        raise pyjwt.InvalidIssuerError('bad issuer')

    monkeypatch.setattr(govbr_oidc.jwt, 'decode', _fake_decode)

    with pytest.raises(GovBrOIDCError, match='issuer'):
        decode_jwt_payload('a.b.c', config=config)


def test_decode_jwt_payload_verified_maps_invalid_audience(monkeypatch):
    config = _make_config()
    _install_fake_jwks_client(monkeypatch)

    def _fake_decode(*args, **kwargs):
        raise pyjwt.InvalidAudienceError('bad aud')

    monkeypatch.setattr(govbr_oidc.jwt, 'decode', _fake_decode)

    with pytest.raises(GovBrOIDCError, match='audience'):
        decode_jwt_payload('a.b.c', config=config)


def test_decode_jwt_payload_verified_maps_generic_invalid_token(monkeypatch):
    config = _make_config()
    _install_fake_jwks_client(monkeypatch)

    def _fake_decode(*args, **kwargs):
        raise pyjwt.InvalidTokenError('algorithm mismatch')

    monkeypatch.setattr(govbr_oidc.jwt, 'decode', _fake_decode)

    with pytest.raises(GovBrOIDCError, match='inválido'):
        decode_jwt_payload('a.b.c', config=config)


def test_decode_jwt_payload_verified_wraps_jwks_failure(monkeypatch):
    config = _make_config()

    def _broken_client(jwks_uri):
        raise RuntimeError('kaboom')

    monkeypatch.setattr(govbr_oidc, '_get_jwks_client', _broken_client)

    with pytest.raises(GovBrOIDCError, match='chave pública'):
        decode_jwt_payload('a.b.c', config=config)


# ---------------------------------------------------------------------------
# Cache de PyJWKClient
# ---------------------------------------------------------------------------


def test_jwks_client_is_cached(monkeypatch):
    govbr_oidc._jwks_client_cache.clear()

    built = []

    class FakePyJWKClient:
        def __init__(self, uri, cache_keys=True, lifespan=None):
            built.append(uri)

    monkeypatch.setattr(govbr_oidc, 'PyJWKClient', FakePyJWKClient)

    first = _get_jwks_client('https://idp/keys')
    second = _get_jwks_client('https://idp/keys')

    assert first is second
    assert built == ['https://idp/keys']


def test_jwks_client_cache_invalidates_after_ttl(monkeypatch):
    govbr_oidc._jwks_client_cache.clear()

    built = []

    class FakePyJWKClient:
        def __init__(self, uri, cache_keys=True, lifespan=None):
            built.append(uri)

    monkeypatch.setattr(govbr_oidc, 'PyJWKClient', FakePyJWKClient)

    fake_now = [1000.0]
    monkeypatch.setattr(govbr_oidc.time, 'monotonic', lambda: fake_now[0])

    _get_jwks_client('https://idp/keys')
    fake_now[0] += govbr_oidc._JWKS_CACHE_TTL + 5
    _get_jwks_client('https://idp/keys')

    assert built == ['https://idp/keys', 'https://idp/keys']


# ---------------------------------------------------------------------------
# Settings / habilitação
# ---------------------------------------------------------------------------


def test_is_govbr_oidc_enabled_requires_all_mandatory_fields():
    assert govbr_oidc.is_govbr_oidc_enabled({'GOVBR_OIDC_ENABLED': False}) is False
    assert govbr_oidc.is_govbr_oidc_enabled(_make_config()) is True

    incomplete = _make_config({'GOVBR_OIDC_CLIENT_SECRET': ''})
    assert govbr_oidc.is_govbr_oidc_enabled(incomplete) is False


def test_get_govbr_oidc_settings_populates_endpoints():
    settings = govbr_oidc.get_govbr_oidc_settings(_make_config())

    assert settings.authorization_endpoint.endswith('/protocol/openid-connect/auth')
    assert settings.token_endpoint.endswith('/protocol/openid-connect/token')
    assert settings.userinfo_endpoint.endswith('/protocol/openid-connect/userinfo')
    assert settings.logout_endpoint.endswith('/protocol/openid-connect/logout')
    assert settings.jwks_uri.endswith('/protocol/openid-connect/certs')
    assert settings.issuer == 'https://idp.example.com/auth/realms/my-realm'


def test_get_govbr_oidc_settings_when_disabled_raises():
    with pytest.raises(GovBrOIDCError):
        govbr_oidc.get_govbr_oidc_settings({'GOVBR_OIDC_ENABLED': False})
