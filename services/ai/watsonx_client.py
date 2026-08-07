"""Única fronteira do app com o provedor IBM watsonx.ai (``langchain-ibm``).

O import do SDK é lazy (dentro de função): a lib pode não estar instalada e o
app não pode quebrar no boot. Qualquer falha (credencial, dependência, rede,
timeout) vira ``SugestaoIndisponivel`` com log estruturado — nunca vaza
exceção crua para a rota.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from flask import current_app

if TYPE_CHECKING:
    from langchain_ibm import ChatWatsonx

WATSONX_URL_PADRAO = "https://us-south.ml.cloud.ibm.com"
MODELO_SUGESTOES_PADRAO = "mistralai/mistral-small-3-1-24b-instruct-2503"
# Medido em campo (2026-08-07): 200 projetos geram ~3.030 tokens de saída em
# ~35s; 3000 truncava o JSON e 30s de time_limit virava 500 no vLLM da IBM.
MAX_TOKENS_SUGESTOES_PADRAO = 6000
TIMEOUT_WATSONX_SEGUNDOS = 120
MAX_RETRIES_WATSONX = 1


class SugestaoIndisponivel(Exception):
    """Sugestão de IA não pôde ser gerada — a rota mapeia para 503/502."""


class ClienteChatIA(Protocol):
    """Contrato do cliente de chat injetável (fake nomeado nos testes)."""

    def invocar(self, system_prompt: str, user_prompt: str) -> str: ...


def ia_habilitada() -> bool:
    """Feature flag implícita: sem as DUAS credenciais a IA fica invisível."""
    return bool(
        os.environ.get("WATSONX_API_KEY") and os.environ.get("WATSONX_PROJECT_ID")
    )


def modelo_sugestoes_configurado() -> str:
    """Model id efetivo (env ou padrão) — compõe o ``input_hash`` do cache."""
    return os.environ.get("AI_SUGGESTIONS_MODEL_ID", MODELO_SUGESTOES_PADRAO)


@dataclass(frozen=True)
class _ConfigWatsonx:
    api_key: str
    project_id: str
    url: str
    model_id: str
    max_tokens: int


def _carregar_config_watsonx() -> _ConfigWatsonx:
    api_key = os.environ.get("WATSONX_API_KEY", "")
    project_id = os.environ.get("WATSONX_PROJECT_ID", "")
    if not api_key or not project_id:
        raise SugestaoIndisponivel(
            "credenciais watsonx ausentes: defina WATSONX_API_KEY e WATSONX_PROJECT_ID"
        )
    return _ConfigWatsonx(
        api_key=api_key,
        project_id=project_id,
        url=os.environ.get("WATSONX_URL", WATSONX_URL_PADRAO),
        model_id=modelo_sugestoes_configurado(),
        max_tokens=int(
            os.environ.get(
                "AI_SUGGESTIONS_MAX_TOKENS", str(MAX_TOKENS_SUGESTOES_PADRAO)
            )
        ),
    )


def _params_chat_json(max_tokens: int) -> dict[str, object]:
    return {
        "temperature": 0,
        "max_tokens": max_tokens,
        # Quebra loop degenerativo em temperature 0 ("saúde, saúde, ...").
        "frequency_penalty": 0.2,
        # time_limit em ms: timeout server-side do watsonx, além do retry local.
        "time_limit": TIMEOUT_WATSONX_SEGUNDOS * 1000,
        "response_format": {"type": "json_object"},
    }


def _importar_chat_watsonx() -> type["ChatWatsonx"]:
    try:
        from langchain_ibm import ChatWatsonx
    except ImportError as exc:
        _log_falha_watsonx("(import)", "import", exc)
        raise SugestaoIndisponivel(
            "dependência langchain-ibm não instalada; instale-a para habilitar a IA"
        ) from exc
    return ChatWatsonx


def _construir_chat_watsonx(config: _ConfigWatsonx) -> "ChatWatsonx":
    chat_watsonx = _importar_chat_watsonx()
    try:
        return chat_watsonx(
            model_id=config.model_id,
            url=config.url,
            apikey=config.api_key,
            project_id=config.project_id,
            params=_params_chat_json(config.max_tokens),
        )
    except Exception as exc:
        _log_falha_watsonx(config.model_id, "construcao", exc)
        raise SugestaoIndisponivel(
            f"falha ao configurar o cliente watsonx (model_id={config.model_id})"
        ) from exc


def _log_falha_watsonx(model_id: str, etapa: str, exc: Exception) -> None:
    current_app.logger.error(
        "watsonx indisponível",
        extra={"model_id": model_id, "etapa": etapa, "erro": type(exc).__name__},
        exc_info=exc,
    )


class WatsonxChatClient:
    """Cliente real de chat; implementa ``ClienteChatIA``.

    Exemplo: ``WatsonxChatClient().invocar(system, user)`` → texto cru da
    resposta (o parse fica com ``suggestion_schema``).
    """

    def invocar(self, system_prompt: str, user_prompt: str) -> str:
        config = _carregar_config_watsonx()
        chat = _construir_chat_watsonx(config)
        ultimo_erro: Exception | None = None
        for tentativa in range(MAX_RETRIES_WATSONX + 1):
            try:
                resposta = chat.invoke(
                    [("system", system_prompt), ("human", user_prompt)]
                )
                return str(resposta.content)
            except Exception as exc:
                ultimo_erro = exc
                if _erro_de_deadline(exc):
                    _log_falha_watsonx(config.model_id, "deadline", exc)
                    raise SugestaoIndisponivel(
                        "time_limit do watsonx estourou — erro determinístico, "
                        "sem retry; revise TIMEOUT_WATSONX_SEGUNDOS/max_tokens"
                    ) from exc
                _log_falha_watsonx(config.model_id, f"invocacao_{tentativa}", exc)
        raise SugestaoIndisponivel(
            f"provedor watsonx falhou após {MAX_RETRIES_WATSONX + 1} tentativas"
        ) from ultimo_erro


def _erro_de_deadline(exc: Exception) -> bool:
    """Deadline estourado é erro de configuração: retry só re-paga o prefill."""
    texto = str(exc).casefold()
    return "context deadline exceeded" in texto or "time limit" in texto
