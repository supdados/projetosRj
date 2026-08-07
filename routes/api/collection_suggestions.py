"""Endpoints JSON das SUGESTÕES DE COLEÇÕES por IA (plano IA Fase 2).

Extraído de ``routes/api/collections.py`` (mesmo ``main_bp``, nenhuma URL
mudou). Cache persistido em ``colecao_sugestao_ia``:

    - ``GET  /api/colecoes/sugestoes``                      — serve o lote pendente; nunca chama LLM.
    - ``POST /api/colecoes/sugestoes``                      — gera via watsonx e substitui o lote.
    - ``POST /api/colecoes/sugestoes/<id>/descartar``       — descarte persistente.

O aceite fica no ``POST /api/colecoes`` (``routes/api/collections.py``), campo
``sugestao_id``. Spec: ``docs/plano-ia-fase2-cache-sugestoes.md`` §3.3.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from flask import g, request

from models import ColecaoSugestaoIA, db
from services.ai import (
    ProjetoCandidato,
    ProjetosInsuficientes,
    SugestaoIndisponivel,
    SugestoesGeradas,
    calcular_input_hash,
    coletar_projetos_candidatos,
    descartar_sugestao,
    ia_habilitada,
    lote_pendente,
    modelo_sugestoes_configurado,
    persistir_lote,
    sugerir_colecoes,
)
from time_utils import iso_utc, utc_now

from ..blueprint import main_bp
from .collections import _ApiResponse, _mutar
from .envelope import fail, fail_internal, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import serialize_colecao_sugestao

_IA_DESLIGADA = "Sugestões por IA indisponíveis nesta instalação."
_IA_FALHOU = "Não foi possível gerar sugestões agora. Tente novamente."
_IA_POUCOS_PROJETOS = (
    "É preciso ter acesso a pelo menos 2 projetos para gerar sugestões."
)

_JANELA_DEDUPE_SUGESTOES = timedelta(seconds=60)


@main_bp.route("/api/colecoes/sugestoes", methods=["GET"])
@api_login_required
def api_colecao_sugestoes_get() -> _ApiResponse:
    """Serve o lote pendente do cache; NUNCA chama o LLM (plano IA Fase 2 §3.3).

    Sem lote responde 200 com ``sugestoes: []`` — a UI mostra o CTA de gerar e
    não dispara o POST sozinha. ``desatualizado`` compara o ``input_hash`` do
    lote com o hash da carteira visível atual.
    """
    if not ia_habilitada():
        return fail(_IA_DESLIGADA, status=503, code="sugestoes_indisponiveis")
    projetos = coletar_projetos_candidatos(g.user)
    hash_atual = calcular_input_hash(projetos, modelo_sugestoes_configurado())
    return ok(_payload_do_lote(lote_pendente(g.user.id), projetos, hash_atual))


def _payload_do_lote(
    linhas: list[ColecaoSugestaoIA],
    projetos: list[ProjetoCandidato],
    hash_atual: str,
) -> dict[str, Any]:
    """Shape único de GET e POST; sem lote, ``gerado_em``/``lote_id`` são null."""
    primeira = linhas[0] if linhas else None
    return {
        "sugestoes": [serialize_colecao_sugestao(linha) for linha in linhas],
        "projetos": [{"id": p.id, "titulo": p.titulo} for p in projetos],
        "gerado_em": iso_utc(primeira.created_at) if primeira else None,
        "lote_id": primeira.lote_id if primeira else None,
        "desatualizado": primeira is not None and primeira.input_hash != hash_atual,
    }


@main_bp.route("/api/colecoes/sugestoes", methods=["POST"])
@api_login_required
def api_colecao_sugestoes() -> _ApiResponse:
    """Gera sugestões via LLM e substitui o lote pendente (mesmo shape do GET).

    REGRA DURA (plano IA Fase 2, risco #2): nenhuma escrita em ``db.session``
    antes da chamada ao LLM — SQLite sem WAL seguraria um write lock pelos ~45s
    do provedor. Fluxo: gerar → persistir → UM commit. Lote pendente com o
    mesmo ``input_hash`` e menos de 60s é devolvido sem regenerar (dedupe de
    duplo-clique/F5); body opcional ``{"forcar": true}`` pula a guarda. Sem
    credencial responde 503; falha ou resposta inválida do provedor vira 502.
    """
    if not ia_habilitada():
        return fail(_IA_DESLIGADA, status=503, code="sugestoes_indisponiveis")
    lote_fresco = _lote_fresco_para_dedupe()
    if lote_fresco is not None:
        return ok(lote_fresco)
    try:
        resultado = sugerir_colecoes(g.user)
    except ProjetosInsuficientes:
        return fail(_IA_POUCOS_PROJETOS, status=422, code="validation")
    except SugestaoIndisponivel as exc:
        return fail_internal(
            exc, "sugerir coleções", status=502, public_message=_IA_FALHOU
        )
    return _mutar(
        lambda: ok(_persistir_lote_payload(resultado)),
        "persistir sugestões de coleções",
    )


def _forcar_regeneracao() -> bool:
    payload = request.get_json(silent=True)
    return isinstance(payload, dict) and bool(payload.get("forcar"))


def _lote_fresco_para_dedupe() -> dict[str, Any] | None:
    """Lote pendente com o mesmo input e < 60s: devolvê-lo em vez de regenerar."""
    if _forcar_regeneracao():
        return None
    linhas = lote_pendente(g.user.id)
    if not linhas or utc_now() - linhas[0].created_at >= _JANELA_DEDUPE_SUGESTOES:
        return None
    projetos = coletar_projetos_candidatos(g.user)
    hash_atual = calcular_input_hash(projetos, modelo_sugestoes_configurado())
    if linhas[0].input_hash != hash_atual:
        return None
    return _payload_do_lote(linhas, projetos, hash_atual)


def _persistir_lote_payload(resultado: SugestoesGeradas) -> dict[str, Any]:
    # flush para as linhas ganharem id/created_at antes de serializar
    linhas = persistir_lote(g.user.id, resultado)
    db.session.flush()
    payload = _payload_do_lote(
        linhas, resultado.projetos_analisados, resultado.input_hash
    )
    if not linhas:
        # lote sem novidade (tudo já aceito/descartado): UI não reoferece o CTA
        payload["gerado_em"] = iso_utc(utc_now())
    return payload


@main_bp.route("/api/colecoes/sugestoes/<int:sugestao_id>/descartar", methods=["POST"])
@api_login_required
def api_colecao_sugestao_descartar(sugestao_id: int) -> _ApiResponse:
    """Marca a sugestão como descartada; o conjunto não volta a ser sugerido.

    SEM gate de IA de propósito: descartar cache existente deve funcionar mesmo
    com a credencial removida. Inexistente ou alheia responde 404
    anti-enumeração (mesmo contrato de ``_load_acesso``).
    """
    return _mutar(
        lambda: _descartar_e_confirmar(sugestao_id),
        "descartar sugestão de coleção",
    )


def _descartar_e_confirmar(sugestao_id: int) -> _ApiResponse:
    if not descartar_sugestao(g.user.id, sugestao_id):
        return fail_not_found()
    return ok()
