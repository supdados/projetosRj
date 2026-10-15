"""Liga/desliga das integrações opcionais e o resumo de boot.

Fixa o contrato combinado para produção: flag AUSENTE = comportamento de
antes (segue a credencial); `0` força OFF; `1` sem credencial continua OFF.
"""

from __future__ import annotations

import logging

import pytest
from flask import Flask

import services.integrations_status as integrations_status
from config import resolve_integration_flag
from services.ai.watsonx_client import ia_habilitada
from services.integrations_status import (
    IntegrationStatus,
    collect_integration_statuses,
    format_integration_summary,
    log_integration_statuses,
)
from services.siorg_client import siorg_habilitado


@pytest.mark.parametrize(
    ("raw", "configurado", "esperado"),
    [
        (None, True, True),
        ("", True, True),
        ("", False, False),
        ("1", True, True),
        ("1", False, False),
        ("0", True, False),
        ("false", True, False),
        (" OFF ", True, False),
    ],
)
def test_resolve_integration_flag(raw, configurado, esperado):
    assert resolve_integration_flag(raw, configurado=configurado) is esperado


def test_ia_habilitada_segue_credenciais_sem_flag(monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "chave")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "projeto")

    assert ia_habilitada() is True


def test_ia_habilitada_flag_zero_desliga_mesmo_com_credenciais(monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "chave")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "projeto")
    monkeypatch.setenv("WATSONX_ENABLED", "0")

    assert ia_habilitada() is False


def test_ia_habilitada_flag_um_sem_credenciais_continua_off(monkeypatch):
    monkeypatch.setenv("WATSONX_ENABLED", "1")

    assert ia_habilitada() is False


def test_siorg_habilitado_respeita_flag():
    assert siorg_habilitado({"SIORG_API_KEY": "tok"}) is True
    assert siorg_habilitado({"SIORG_API_KEY": "tok", "SIORG_ENABLED": "0"}) is False
    assert siorg_habilitado({"SIORG_API_KEY": "", "SIORG_ENABLED": "1"}) is False


def _config_tudo_desligado() -> dict[str, object]:
    return {
        "GOVBR_OIDC_ENABLED": False,
        "GOOGLE_CALENDAR_ENABLED": False,
        "SIORG_API_KEY": "",
        "SIORG_ENABLED": "",
        "CHATBOT_ENABLED": False,
        "CHATBOT_BASE_URL": "",
        "CONVITES_HABILITADOS": False,
    }


def test_collect_integration_statuses_tudo_desligado():
    statuses = collect_integration_statuses(_config_tudo_desligado())

    assert [s.nome for s in statuses] == [
        "Gov.br",
        "Google Calendar",
        "watsonx",
        "SIORG",
        "Chatbot",
        "Convites",
    ]
    assert not any(s.ligada or s.pedida for s in statuses)


def test_collect_marca_pedida_sem_credencial():
    config = {
        **_config_tudo_desligado(),
        "GOVBR_OIDC_ENABLED": True,
        "CHATBOT_ENABLED": True,
    }

    por_nome = {s.nome: s for s in collect_integration_statuses(config)}

    assert por_nome["Gov.br"].pedida and not por_nome["Gov.br"].ligada
    assert por_nome["Chatbot"].pedida and not por_nome["Chatbot"].ligada


def test_format_integration_summary():
    statuses = [
        IntegrationStatus("Gov.br", False, False, ""),
        IntegrationStatus("SIORG", True, False, ""),
    ]

    assert format_integration_summary(statuses) == "Integrações: Gov.br=OFF · SIORG=ON"


def _app_com_config(**config: object) -> Flask:
    flask_app = Flask(__name__)
    flask_app.config.update(_config_tudo_desligado())
    flask_app.config.update(config)
    return flask_app


def test_log_avisa_integracao_pedida_sem_credencial(caplog):
    flask_app = _app_com_config(GOVBR_OIDC_ENABLED=True)

    with caplog.at_level(logging.INFO, logger=flask_app.logger.name):
        log_integration_statuses(flask_app)

    mensagens = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("Integrações: Gov.br=OFF") for m in mensagens)
    assert any("Gov.br ligada no .env mas desativada" in m for m in mensagens)


def _coleta_que_quebra(_config: object) -> list[IntegrationStatus]:
    raise RuntimeError("config ilegível")


def test_log_nunca_derruba_o_boot(monkeypatch, caplog):
    monkeypatch.setattr(
        integrations_status, "collect_integration_statuses", _coleta_que_quebra
    )
    flask_app = _app_com_config()

    with caplog.at_level(logging.ERROR, logger=flask_app.logger.name):
        log_integration_statuses(flask_app)

    assert any("resumo de integrações" in r.getMessage() for r in caplog.records)
