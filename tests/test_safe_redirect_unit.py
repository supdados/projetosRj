"""Regressão de Open Redirect (CWE-601) para routes.safe_redirect.safe_internal_path.

Cobre os vetores que escapavam da validação antiga: '//evil.com' e '/\\evil.com'
(barra invertida que os navegadores normalizam para host externo).
"""

import pytest

from routes.safe_redirect import safe_internal_path

HOST = "projetos.rj.gov.br"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("/projetos/5", "/projetos/5"),
        ("/projetos?area=1&page=2", "/projetos?area=1&page=2"),
        ("/", "/"),
        ("  /projetos  ", "/projetos"),  # strip de espaços
        (f"https://{HOST}/projetos", "/projetos"),  # absoluto mesmo host -> relativo
        (f"https://{HOST}/a?b=c", "/a?b=c"),
    ],
)
def test_accepts_same_host_targets(raw, expected):
    assert safe_internal_path(raw, HOST) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "//evil.com",  # protocol-relative
        "/\\evil.com",  # barra invertida normalizada p/ '//' pelos navegadores
        "/\\/evil.com",
        "\\evil.com",
        "https://evil.com/phish",  # host externo explícito
        "http://evil.com",
        "javascript:alert(1)",  # scheme não-http
        "ftp://projetos.rj.gov.br/x",
        "data:text/html,<script>1</script>",
    ],
)
def test_rejects_open_redirect_vectors(raw):
    assert safe_internal_path(raw, HOST) is None


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_rejects_empty(raw):
    assert safe_internal_path(raw, HOST) is None


def test_other_host_with_same_path_is_rejected():
    assert safe_internal_path("https://evil.com/projetos/5", HOST) is None


def test_host_with_port_must_match_exactly():
    assert safe_internal_path("http://projetos.rj.gov.br:8080/x", HOST) is None
    assert safe_internal_path("http://projetos.rj.gov.br:8080/x", "projetos.rj.gov.br:8080") == "/x"
