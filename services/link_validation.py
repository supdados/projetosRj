"""Validação de rótulo e URL de links customizados de um projeto.

Allowlist http/https (nunca denylist — OWASP), ``strip()`` antes de
``urlparse`` (defesa contra CVE-2023-24329) e rejeição de userinfo
(``https://confiavel.com@evil.com``). Compartilhado pelos 3 links fixos
e pelos links personalizados.
"""

from __future__ import annotations

from urllib.parse import urlparse

CUSTOM_LINK_MAX_PER_PROJECT = 3
LINK_LABEL_MAX = 80
LINK_URL_MAX = 500

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class LinkValidationError(ValueError):
    """Rótulo ou URL de link inválido (scheme, userinfo ou tamanho)."""


def _invalid_url(received: str, reason: str) -> LinkValidationError:
    return LinkValidationError(
        f"URL inválida {received!r}: {reason} "
        f"(esperado: http(s)://dominio, até {LINK_URL_MAX} caracteres)."
    )


def normalize_link_url(value: str | None) -> str | None:
    """Normaliza uma URL de usuário: vazio -> None, prefixa 'https://' quando falta.

    Ex.: ``normalize_link_url('example.com') == 'https://example.com'``.
    Rejeita scheme fora de http/https, netloc vazio, userinfo e > 500 chars.
    """
    if value is not None and not isinstance(value, str):
        raise _invalid_url(str(value), f"tipo {type(value).__name__} não suportado")
    stripped = (value or "").strip()
    if not stripped:
        return None
    # urlparse levanta ValueError cru p/ netloc malformado (ex.: "https://[foo").
    try:
        parsed = urlparse(stripped)
        if not parsed.scheme and ":" not in stripped:
            stripped = f"https://{stripped}"
            parsed = urlparse(stripped)
    except ValueError:
        raise _invalid_url(stripped, "não parseável") from None
    if len(stripped) > LINK_URL_MAX:
        raise _invalid_url(stripped, f"excede {LINK_URL_MAX} caracteres")
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise _invalid_url(stripped, f"scheme {parsed.scheme!r} não permitido")
    if not parsed.netloc:
        raise _invalid_url(stripped, "domínio ausente")
    if parsed.username or parsed.password:
        raise _invalid_url(stripped, "userinfo não permitido")
    return stripped


def normalize_link_label(value: str) -> str:
    """Normaliza o rótulo: ``strip()``; vazio ou > 80 chars -> erro.

    Ex.: ``normalize_link_label('  Painel BI ') == 'Painel BI'``.
    """
    if value is not None and not isinstance(value, str):
        raise LinkValidationError(
            f"Rótulo de link inválido {value!r}: tipo {type(value).__name__} "
            "não suportado (esperado: texto)."
        )
    label = (value or "").strip()
    if not label:
        raise LinkValidationError("Rótulo de link vazio (esperado: texto não vazio).")
    if len(label) > LINK_LABEL_MAX:
        raise LinkValidationError(
            f"Rótulo de link {label!r} excede {LINK_LABEL_MAX} caracteres."
        )
    return label
