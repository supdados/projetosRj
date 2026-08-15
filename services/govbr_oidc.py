import json
import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from jwt import PyJWKClient


class GovBrOIDCError(RuntimeError):
    """Erro de integração com o provedor OIDC gov.br/RHSSO."""


@dataclass(frozen=True)
class GovBrOIDCSettings:
    base_url: str
    realm: str
    client_id: str
    client_secret: str
    redirect_uri: str
    post_logout_redirect_uri: str
    scope: str
    timeout_seconds: int

    @property
    def authorization_endpoint(self):
        return f"{self.base_url}/auth/realms/{self.realm}/protocol/openid-connect/auth"

    @property
    def token_endpoint(self):
        return f"{self.base_url}/auth/realms/{self.realm}/protocol/openid-connect/token"

    @property
    def userinfo_endpoint(self):
        return (
            f"{self.base_url}/auth/realms/{self.realm}/protocol/openid-connect/userinfo"
        )

    @property
    def logout_endpoint(self):
        return (
            f"{self.base_url}/auth/realms/{self.realm}/protocol/openid-connect/logout"
        )

    @property
    def jwks_uri(self):
        return f"{self.base_url}/auth/realms/{self.realm}/protocol/openid-connect/certs"

    @property
    def issuer(self):
        return f"{self.base_url}/auth/realms/{self.realm}"


def _as_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_base_url(base_url):
    if not base_url:
        return ""
    return str(base_url).strip().rstrip("/")


def _normalize_timeout(raw_value):
    try:
        timeout = int(raw_value)
    except (TypeError, ValueError):
        return 10
    if timeout <= 0:
        return 10
    return timeout


def is_govbr_oidc_enabled(config):
    if not _as_bool(config.get("GOVBR_OIDC_ENABLED", False)):
        return False

    required = (
        "GOVBR_OIDC_BASE_URL",
        "GOVBR_OIDC_REALM",
        "GOVBR_OIDC_CLIENT_ID",
        "GOVBR_OIDC_CLIENT_SECRET",
        "GOVBR_OIDC_REDIRECT_URI",
    )
    return all(str(config.get(key, "")).strip() for key in required)


def get_govbr_oidc_settings(config):
    if not is_govbr_oidc_enabled(config):
        raise GovBrOIDCError("Integração gov.br não está habilitada ou configurada.")

    return GovBrOIDCSettings(
        base_url=_normalize_base_url(config.get("GOVBR_OIDC_BASE_URL")),
        realm=str(config.get("GOVBR_OIDC_REALM", "")).strip(),
        client_id=str(config.get("GOVBR_OIDC_CLIENT_ID", "")).strip(),
        client_secret=str(config.get("GOVBR_OIDC_CLIENT_SECRET", "")).strip(),
        redirect_uri=str(config.get("GOVBR_OIDC_REDIRECT_URI", "")).strip(),
        post_logout_redirect_uri=str(
            config.get("GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI", "")
        ).strip(),
        scope=str(config.get("GOVBR_OIDC_SCOPE", "openid profile email")).strip()
        or "openid profile email",
        timeout_seconds=_normalize_timeout(
            config.get("GOVBR_OIDC_TIMEOUT_SECONDS", 10)
        ),
    )


def normalize_cpf(raw_value):
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value:
        return None

    digits = "".join(char for char in value if char.isdigit())
    if len(digits) != 11:
        raise ValueError("CPF deve conter exatamente 11 dígitos.")
    return digits


def format_cpf(cpf_digits):
    cpf = normalize_cpf(cpf_digits)
    if cpf is None:
        return ""
    return f"{cpf[0:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}"


_jwks_client_cache = {}
_JWKS_CACHE_TTL = 3600


def _get_jwks_client(jwks_uri):
    now = time.monotonic()
    cached = _jwks_client_cache.get(jwks_uri)
    if cached and (now - cached[1]) < _JWKS_CACHE_TTL:
        return cached[0]
    client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=_JWKS_CACHE_TTL)
    _jwks_client_cache[jwks_uri] = (client, now)
    return client


def decode_jwt_payload(token, *, config):
    """Decodifica e valida o ID token JWT com verificação completa.

    Sempre valida assinatura via JWKS, issuer, audience e expiração —
    não existe caminho de decode sem verificação de assinatura.
    """
    if not token or token.count(".") < 2:
        raise GovBrOIDCError("ID token inválido.")

    return _decode_jwt_verified(token, config)


def _decode_jwt_verified(token, config):
    settings = get_govbr_oidc_settings(config)
    try:
        jwks_client = _get_jwks_client(settings.jwks_uri)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except Exception as exc:
        raise GovBrOIDCError(
            f"Falha ao obter chave pública do IdP para validar ID token: {exc}"
        ) from exc

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.client_id,
            issuer=settings.issuer,
            leeway=timedelta(seconds=30),
            options={
                "require": ["exp", "iss", "aud", "sub"],
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise GovBrOIDCError("ID token expirado.") from exc
    except jwt.InvalidIssuerError as exc:
        raise GovBrOIDCError("ID token com issuer inválido.") from exc
    except jwt.InvalidAudienceError as exc:
        raise GovBrOIDCError("ID token com audience inválido.") from exc
    except jwt.InvalidTokenError as exc:
        raise GovBrOIDCError(f"ID token inválido: {exc}") from exc

    return payload


def build_authorization_url(config, *, state, nonce):
    settings = get_govbr_oidc_settings(config)
    params = {
        "response_type": "code",
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "scope": settings.scope,
        "state": state,
        "nonce": nonce,
    }
    return f"{settings.authorization_endpoint}?{urlencode(params)}"


def _decode_response_body(raw_body):
    if raw_body is None:
        return ""
    if isinstance(raw_body, bytes):
        return raw_body.decode("utf-8", errors="replace")
    return str(raw_body)


def _http_json_request(*, method, url, timeout_seconds, headers=None, form_data=None):
    request_headers = dict(headers or {})
    data = None
    if form_data is not None:
        data = urlencode(form_data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            raw_body = response.read()
            body = _decode_response_body(raw_body)
    except HTTPError as exc:
        body = _decode_response_body(exc.read())
        raise GovBrOIDCError(
            f"Erro HTTP do provedor OIDC ({exc.code}) em {url}: {body[:300]}"
        ) from exc
    except URLError as exc:
        raise GovBrOIDCError(
            f"Falha de conectividade com o provedor OIDC: {exc}"
        ) from exc
    except Exception as exc:
        raise GovBrOIDCError(
            f"Erro inesperado ao chamar o provedor OIDC: {exc}"
        ) from exc

    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError as exc:
        raise GovBrOIDCError(
            "Resposta do provedor OIDC não está em JSON válido."
        ) from exc

    if not isinstance(payload, dict):
        raise GovBrOIDCError("Resposta do provedor OIDC em formato inválido.")
    return payload


def exchange_code_for_tokens(config, *, code):
    settings = get_govbr_oidc_settings(config)
    payload = _http_json_request(
        method="POST",
        url=settings.token_endpoint,
        timeout_seconds=settings.timeout_seconds,
        form_data={
            "grant_type": "authorization_code",
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "code": code,
            "redirect_uri": settings.redirect_uri,
        },
    )
    if "access_token" not in payload:
        raise GovBrOIDCError("Resposta de token sem access_token.")
    return payload


def fetch_userinfo(config, *, access_token):
    settings = get_govbr_oidc_settings(config)
    payload = _http_json_request(
        method="GET",
        url=settings.userinfo_endpoint,
        timeout_seconds=settings.timeout_seconds,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if "sub" not in payload:
        raise GovBrOIDCError("Resposta do userinfo sem claim sub.")
    return payload


def build_logout_url(config, *, id_token_hint, post_logout_redirect_uri=None):
    settings = get_govbr_oidc_settings(config)
    redirect_uri = (
        post_logout_redirect_uri or settings.post_logout_redirect_uri
    ).strip()
    if not redirect_uri:
        raise GovBrOIDCError("post_logout_redirect_uri não configurado.")

    params = {
        "post_logout_redirect_uri": redirect_uri,
        "id_token_hint": id_token_hint,
    }
    return f"{settings.logout_endpoint}?{urlencode(params)}"
