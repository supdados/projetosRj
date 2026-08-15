"""ProxyFix por ambiente (sprint 6.4).

Fixa que o default é DESLIGADO (comportamento local idêntico ao de hoje) e que,
quando ligado, scheme/Host passam a vir dos X-Forwarded-* do proxy.
"""

from __future__ import annotations

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app import _apply_proxy_fix, create_app
from config import _env_proxy_hops

PROBE_PATH = "/__proxyfix_probe"


def _app_com_proxy(**config_extra: object) -> Flask:
    """App real (create_app) com uma rota-sonda que ecoa scheme/host efetivos."""
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SKIP_STARTUP_DB_INIT": True,
            "WTF_CSRF_ENABLED": False,
            **config_extra,
        }
    )

    @flask_app.route(PROBE_PATH)
    def _proxyfix_probe() -> str:
        return f"{request.scheme}|{request.host}"

    return flask_app


def _sondar(flask_app: Flask) -> str:
    resposta = flask_app.test_client().get(
        PROBE_PATH,
        base_url="http://interno.local",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "publico.rj.gov.br",
            "X-Forwarded-For": "203.0.113.7",
        },
    )
    return resposta.get_data(as_text=True)


def test_proxyfix_desligado_por_padrao_ignora_forwarded() -> None:
    flask_app = _app_com_proxy()
    assert not isinstance(flask_app.wsgi_app, ProxyFix)
    assert _sondar(flask_app) == "http|interno.local"


def test_proxyfix_ligado_adota_scheme_e_host_do_proxy() -> None:
    flask_app = _app_com_proxy(PROXYFIX_ENABLED=True)
    assert isinstance(flask_app.wsgi_app, ProxyFix)
    assert _sondar(flask_app) == "https|publico.rj.gov.br"


def test_proxyfix_ligado_com_x_host_zero_preserva_o_host_interno() -> None:
    flask_app = _app_com_proxy(PROXYFIX_ENABLED=True, PROXYFIX_X_HOST=0)
    assert _sondar(flask_app) == "https|interno.local"


def test_apply_proxy_fix_desligado_e_no_op() -> None:
    flask_app = _app_com_proxy(PROXYFIX_ENABLED=False)
    _apply_proxy_fix(flask_app)
    assert not isinstance(flask_app.wsgi_app, ProxyFix)
    assert _sondar(flask_app) == "http|interno.local"


def test_env_proxy_hops_aceita_zero_e_rejeita_lixo(monkeypatch) -> None:
    monkeypatch.setenv("PROXYFIX_TESTE_HOPS", "0")
    assert _env_proxy_hops("PROXYFIX_TESTE_HOPS", default=1) == 0

    monkeypatch.setenv("PROXYFIX_TESTE_HOPS", "3")
    assert _env_proxy_hops("PROXYFIX_TESTE_HOPS", default=1) == 3

    monkeypatch.setenv("PROXYFIX_TESTE_HOPS", "-2")
    assert _env_proxy_hops("PROXYFIX_TESTE_HOPS", default=1) == 1

    monkeypatch.setenv("PROXYFIX_TESTE_HOPS", "nao-e-numero")
    assert _env_proxy_hops("PROXYFIX_TESTE_HOPS", default=1) == 1

    monkeypatch.delenv("PROXYFIX_TESTE_HOPS")
    assert _env_proxy_hops("PROXYFIX_TESTE_HOPS", default=1) == 1
