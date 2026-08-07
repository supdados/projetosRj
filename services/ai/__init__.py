"""Camada de IA do app — provedor encapsulado em ``watsonx_client``."""

from services.ai.collection_suggestions import (
    HASH_VERSION,
    ProjetoCandidato,
    ProjetosInsuficientes,
    SugestoesGeradas,
    calcular_input_hash,
    coletar_projetos_candidatos,
    montar_prompt,
    sugerir_colecoes,
)
from services.ai.suggestion_schema import (
    ColecaoSugerida,
    SugestoesInvalidas,
    extrair_json,
    validar_sugestoes,
)
from services.ai.suggestion_store import (
    assinatura_do_conjunto,
    assinaturas_bloqueadas,
    descartar_sugestao,
    lote_pendente,
    marcar_aceita,
    persistir_lote,
)
from services.ai.watsonx_client import (
    ClienteChatIA,
    SugestaoIndisponivel,
    WatsonxChatClient,
    ia_habilitada,
    modelo_sugestoes_configurado,
)

__all__ = [
    "ClienteChatIA",
    "ColecaoSugerida",
    "HASH_VERSION",
    "ProjetoCandidato",
    "ProjetosInsuficientes",
    "SugestaoIndisponivel",
    "SugestoesGeradas",
    "SugestoesInvalidas",
    "WatsonxChatClient",
    "assinatura_do_conjunto",
    "assinaturas_bloqueadas",
    "calcular_input_hash",
    "coletar_projetos_candidatos",
    "descartar_sugestao",
    "extrair_json",
    "ia_habilitada",
    "lote_pendente",
    "marcar_aceita",
    "modelo_sugestoes_configurado",
    "montar_prompt",
    "persistir_lote",
    "sugerir_colecoes",
    "validar_sugestoes",
]
