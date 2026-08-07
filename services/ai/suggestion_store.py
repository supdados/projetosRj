"""Persistência do cache de sugestões de coleção por IA (plano Fase 2 §3.1/§3.3).

Os helpers enfileiram na sessão e NÃO commitam — o commit é do endpoint, no
mesmo padrão de ``registrar_autorizacao`` (``models/authorization_audit.py``).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from uuid import uuid4

from flask import current_app

from models import ColecaoSugestaoIA, db
from models.colecao_sugestao import (
    STATUS_SUGESTAO_ACEITA,
    STATUS_SUGESTAO_DESCARTADA,
    STATUS_SUGESTAO_PENDENTE,
)
from services.ai.suggestion_schema import ColecaoSugerida
from time_utils import utc_now

if TYPE_CHECKING:
    from services.ai.collection_suggestions import SugestoesGeradas


def assinatura_do_conjunto(project_ids: list[int]) -> str:
    """sha256 do CONJUNTO ordenado de ids — chave de supressão ordem-independente.

    Exemplo: ``assinatura_do_conjunto([7, 3]) == assinatura_do_conjunto([3, 7])``.
    """
    canonico = "|".join(str(pid) for pid in sorted(project_ids))
    return hashlib.sha256(canonico.encode()).hexdigest()


def assinaturas_bloqueadas(user_id: int) -> set[str]:
    """Assinaturas já decididas (descartadas OU aceitas) — não re-sugerir."""
    rows = (
        db.session.query(ColecaoSugestaoIA.assinatura)
        .filter(
            ColecaoSugestaoIA.user_id == user_id,
            ColecaoSugestaoIA.status.in_(
                (STATUS_SUGESTAO_DESCARTADA, STATUS_SUGESTAO_ACEITA)
            ),
        )
        .all()
    )
    return {assinatura for (assinatura,) in rows}


def persistir_lote(
    user_id: int, resultado: "SugestoesGeradas"
) -> list[ColecaoSugestaoIA]:
    """Substitui o lote pendente do usuário pelas sugestões novas (sem commit).

    Exemplo: ``linhas = persistir_lote(g.user.id, resultado); db.session.commit()``.
    """
    _deletar_pendentes(user_id)
    lote_id = uuid4().hex
    linhas = [
        _linha_do_lote(user_id, lote_id, ordem, sugestao, resultado)
        for ordem, sugestao in enumerate(resultado.sugestoes)
    ]
    db.session.add_all(linhas)
    return linhas


def _deletar_pendentes(user_id: int) -> None:
    db.session.query(ColecaoSugestaoIA).filter_by(
        user_id=user_id, status=STATUS_SUGESTAO_PENDENTE
    ).delete(synchronize_session=False)


def _linha_do_lote(
    user_id: int,
    lote_id: str,
    ordem: int,
    sugestao: ColecaoSugerida,
    resultado: "SugestoesGeradas",
) -> ColecaoSugestaoIA:
    return ColecaoSugestaoIA(
        user_id=user_id,
        lote_id=lote_id,
        input_hash=resultado.input_hash,
        ordem=ordem,
        nome=sugestao.nome,
        descricao=sugestao.descricao,
        justificativa=sugestao.justificativa,
        project_ids=sugestao.project_ids,
        assinatura=assinatura_do_conjunto(sugestao.project_ids),
        modelo_id=resultado.modelo_id,
    )


def lote_pendente(user_id: int) -> list[ColecaoSugestaoIA]:
    """Linhas pendentes do usuário na ordem original da geração."""
    return (
        db.session.query(ColecaoSugestaoIA)
        .filter_by(user_id=user_id, status=STATUS_SUGESTAO_PENDENTE)
        .order_by(ColecaoSugestaoIA.ordem)
        .all()
    )


def descartar_sugestao(user_id: int, sugestao_id: int) -> bool:
    """Marca a sugestão como descartada; ``False`` se inexistente ou alheia."""
    linha = db.session.get(ColecaoSugestaoIA, sugestao_id)
    if linha is None or linha.user_id != user_id:
        return False
    linha.status = STATUS_SUGESTAO_DESCARTADA
    linha.decidido_em = utc_now()
    return True


def marcar_aceita(user_id: int, sugestao_id: int, colecao_id: int) -> bool:
    """Vincula a sugestão à coleção criada; tolerante — bookkeeping nunca
    derruba uma criação válida (plano Fase 2 §3.3), só loga warning."""
    linha = db.session.get(ColecaoSugestaoIA, sugestao_id)
    if (
        linha is None
        or linha.user_id != user_id
        or linha.status != STATUS_SUGESTAO_PENDENTE
    ):
        current_app.logger.warning(
            "sugestao_id não resolvido no aceite",
            extra={"sugestao_id": sugestao_id, "user_id": user_id},
        )
        return False
    linha.status = STATUS_SUGESTAO_ACEITA
    linha.colecao_id = colecao_id
    linha.decidido_em = utc_now()
    return True
