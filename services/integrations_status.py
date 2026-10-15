"""Resumo, no boot, de quais integrações externas estão ligadas.

Todas são opcionais: o app roda só com login local. O resumo existe porque
cada integração nasceu com um gate diferente (flag explícita, credencial
presente, arquivo de credencial) e "ligada no .env mas sem credencial" ficava
desligada em silêncio — quem instalava não sabia por que a função sumiu.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from flask import Flask

from services.ai.watsonx_client import ia_habilitada
from services.google_calendar import is_google_calendar_enabled
from services.govbr_oidc import is_govbr_oidc_enabled
from services.siorg_client import siorg_habilitado

_VALORES_LIGADOS = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class IntegrationStatus:
    """Estado efetivo de uma integração no processo atual."""

    nome: str
    ligada: bool
    # O .env pediu para ligar (flag explícita ou default ON da integração).
    pedida: bool
    # O que configurar quando ``pedida`` e não ``ligada``.
    falta: str


def _flag_explicitamente_ligada(raw: object) -> bool:
    """`1`/`true`/`yes`/`on` (ou bool True); ausente/vazio não conta como pedido."""
    if isinstance(raw, bool):
        return raw
    return str(raw if raw is not None else "").strip().lower() in _VALORES_LIGADOS


def _chatbot_status(config: Mapping[str, object]) -> IntegrationStatus:
    pedida = bool(config.get("CHATBOT_ENABLED"))
    base_url = str(config.get("CHATBOT_BASE_URL", "") or "").strip()
    return IntegrationStatus(
        "Chatbot", pedida and bool(base_url), pedida, "CHATBOT_BASE_URL"
    )


def collect_integration_statuses(
    config: Mapping[str, object],
) -> list[IntegrationStatus]:
    """Estado de cada integração a partir do config do Flask (e do ambiente, no watsonx).

    Ex.: ``collect_integration_statuses(app.config)[0]`` →
    ``IntegrationStatus(nome="Gov.br", ligada=False, pedida=False, falta=...)``.
    """
    convites = bool(config.get("CONVITES_HABILITADOS"))
    return [
        IntegrationStatus(
            "Gov.br",
            is_govbr_oidc_enabled(config),
            _flag_explicitamente_ligada(config.get("GOVBR_OIDC_ENABLED")),
            "GOVBR_OIDC_BASE_URL/REALM/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI",
        ),
        IntegrationStatus(
            "Google Calendar",
            is_google_calendar_enabled(config),
            _flag_explicitamente_ligada(config.get("GOOGLE_CALENDAR_ENABLED")),
            "arquivo GOOGLE_CALENDAR_CLIENT_SECRET_FILE com client_id/client_secret",
        ),
        IntegrationStatus(
            "watsonx",
            ia_habilitada(),
            _flag_explicitamente_ligada(os.environ.get("WATSONX_ENABLED")),
            "WATSONX_API_KEY e WATSONX_PROJECT_ID",
        ),
        IntegrationStatus(
            "SIORG",
            siorg_habilitado(config),
            _flag_explicitamente_ligada(config.get("SIORG_ENABLED")),
            "SIORG_API_KEY",
        ),
        _chatbot_status(config),
        IntegrationStatus("Convites", convites, convites, ""),
    ]


def format_integration_summary(statuses: Sequence[IntegrationStatus]) -> str:
    """Linha única do log de boot.

    Ex.: ``"Integrações: Gov.br=OFF · Google Calendar=ON · ..."``.
    """
    partes = [f"{s.nome}={'ON' if s.ligada else 'OFF'}" for s in statuses]
    return "Integrações: " + " · ".join(partes)


def log_integration_statuses(app: Flask) -> None:
    """Loga o resumo e avisa cada integração pedida no .env mas sem credencial.

    Nunca derruba o boot: é diagnóstico — falha aqui vira log de erro e o app
    sobe normalmente (gunicorn de produção não pode morrer por causa de log).
    """
    try:
        statuses = collect_integration_statuses(app.config)
    except Exception:
        app.logger.exception("Falha ao montar o resumo de integrações (ignorada)")
        return
    app.logger.info(
        format_integration_summary(statuses),
        extra={"integracoes": {s.nome: s.ligada for s in statuses}},
    )
    for status in statuses:
        if status.pedida and not status.ligada:
            app.logger.warning(
                "Integração %s ligada no .env mas desativada: falta %s",
                status.nome,
                status.falta,
                extra={"integracao": status.nome, "falta": status.falta},
            )
