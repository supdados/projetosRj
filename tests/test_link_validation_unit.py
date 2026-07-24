"""Unitários de ``services/link_validation.py``.

Fixam a allowlist http/https (scheme malicioso rejeitado), a rejeição de
userinfo, a defesa CVE-2023-24329 (espaço antes do scheme) e o prefixo
'https://' automático — paridade com o frontend.
"""

from __future__ import annotations

import pytest

from services.link_validation import (
    LINK_LABEL_MAX,
    LINK_URL_MAX,
    LinkValidationError,
    normalize_link_label,
    normalize_link_url,
)

# ---------------------------------------------------------------------------
# normalize_link_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_url_empty_input_returns_none(raw):
    assert normalize_link_url(raw) is None


def test_url_prefixes_https_when_scheme_missing():
    assert normalize_link_url("example.com/painel") == "https://example.com/painel"


def test_url_keeps_valid_https_verbatim():
    assert normalize_link_url("https://gov.br/rj") == "https://gov.br/rj"


def test_url_keeps_valid_http_verbatim():
    assert normalize_link_url("http://gov.br/rj") == "http://gov.br/rj"


@pytest.mark.parametrize(
    "raw",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://host/file",
    ],
)
def test_url_rejects_non_http_scheme(raw):
    with pytest.raises(LinkValidationError) as excinfo:
        normalize_link_url(raw)
    assert "http(s)://dominio" in str(excinfo.value)


def test_url_rejects_userinfo():
    with pytest.raises(LinkValidationError) as excinfo:
        normalize_link_url("https://confiavel.com@evil.com")
    assert "userinfo" in str(excinfo.value)


def test_url_strips_leading_whitespace_before_parsing():
    # CVE-2023-24329: espaço/whitespace antes do scheme não deve mascarar o scheme.
    assert normalize_link_url("  https://gov.br  ") == "https://gov.br"


def test_url_rejects_missing_netloc():
    with pytest.raises(LinkValidationError):
        normalize_link_url("https://")


def test_url_rejects_malformed_ipv6_netloc():
    # urlparse levanta ValueError cru aqui; deve virar LinkValidationError (422).
    with pytest.raises(LinkValidationError):
        normalize_link_url("https://[foo")


@pytest.mark.parametrize("raw", [123, ["https://gov.br"], {"url": "x"}])
def test_url_rejects_non_string_payload(raw):
    with pytest.raises(LinkValidationError):
        normalize_link_url(raw)


def test_url_rejects_over_length():
    oversized = "https://gov.br/" + "a" * LINK_URL_MAX
    with pytest.raises(LinkValidationError) as excinfo:
        normalize_link_url(oversized)
    assert str(LINK_URL_MAX) in str(excinfo.value)


# ---------------------------------------------------------------------------
# normalize_link_label
# ---------------------------------------------------------------------------


def test_label_strips_surrounding_whitespace():
    assert normalize_link_label("  Painel BI ") == "Painel BI"


@pytest.mark.parametrize("raw", ["", "   "])
def test_label_rejects_empty(raw):
    with pytest.raises(LinkValidationError):
        normalize_link_label(raw)


def test_label_rejects_over_length():
    oversized = "x" * (LINK_LABEL_MAX + 1)
    with pytest.raises(LinkValidationError) as excinfo:
        normalize_link_label(oversized)
    assert str(LINK_LABEL_MAX) in str(excinfo.value)


def test_label_accepts_max_length():
    exact = "y" * LINK_LABEL_MAX
    assert normalize_link_label(exact) == exact


@pytest.mark.parametrize("raw", [123, ["Painel"], {"label": "x"}])
def test_label_rejects_non_string_payload(raw):
    with pytest.raises(LinkValidationError):
        normalize_link_label(raw)
