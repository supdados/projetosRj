"""Trilha de autorização das coleções (``AutorizacaoAudit``, alvo "colecao").

Concessão/alteração/revogação de share, respostas ao convite (aceito,
recusado, saiu), reenvio e itens incluídos/removidos — inclusive os removidos
pela poda, com ``detalhe.motivo``. Enfileira na sessão; o commit é da rota.
"""

from __future__ import annotations

from models import (
    ALVO_COLECAO,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    User,
    registrar_autorizacao,
)


def auditar_item_colecao(
    colecao: ProjectCollection,
    project_id: int,
    evento: str,
    ator: User,
) -> None:
    """Trilha de inclusão/remoção manual de item (o ator é o próprio usuário)."""
    registrar_autorizacao(
        evento=evento,
        # Ação em lote sem destinatário único; a trilha registra o ator.
        user_id=ator.id,
        ator_id=ator.id,
        alvo_tipo=ALVO_COLECAO,
        alvo_id=colecao.id,
        detalhe={"project_id": project_id},
    )


def auditar_share(
    colecao: ProjectCollection,
    share: ProjectCollectionShare,
    evento: str,
    ator: User,
) -> None:
    registrar_autorizacao(
        evento=evento,
        # Share por órgão não tem usuário único; a trilha registra o ator (dono)
        # e o rótulo ``destino`` desambigua a leitura da auditoria.
        user_id=share.user_id or ator.id,
        ator_id=ator.id,
        alvo_tipo=ALVO_COLECAO,
        alvo_id=colecao.id,
        detalhe={
            "destino": "orgao" if share.orgao_id is not None else "user",
            "papel": share.papel,
            "user_id": share.user_id,
            "orgao_id": share.orgao_id,
        },
    )


def auditar_resposta(
    colecao: ProjectCollection,
    ator: User,
    evento: str,
    shares: list[ProjectCollectionShare],
    **extra: int,
) -> None:
    registrar_autorizacao(
        evento=evento,
        user_id=ator.id,
        ator_id=ator.id,
        alvo_tipo=ALVO_COLECAO,
        alvo_id=colecao.id,
        detalhe={
            "share_ids": sorted(share.id for share in shares),
            "papeis": sorted({share.papel for share in shares}),
            **extra,
        },
    )


def auditar_reenvio(
    colecao: ProjectCollection,
    share: ProjectCollectionShare,
    ator: User,
    reconvidados: set[int],
) -> None:
    registrar_autorizacao(
        evento="colecao_convite_reenviado",
        user_id=share.user_id or ator.id,
        ator_id=ator.id,
        alvo_tipo=ALVO_COLECAO,
        alvo_id=colecao.id,
        detalhe={
            "share_id": share.id,
            "destino": "orgao" if share.orgao_id is not None else "user",
            "reconvidados": sorted(reconvidados),
        },
    )


def auditar_poda(
    colecao: ProjectCollection,
    item: ProjectCollectionItem,
    ator: User,
    motivo: str,
) -> None:
    registrar_autorizacao(
        evento="colecao_projeto_removido",
        # O afetado é quem incluiu o item; o ator é quem disparou a mutação.
        user_id=item.added_by_user_id or ator.id,
        ator_id=ator.id,
        alvo_tipo=ALVO_COLECAO,
        alvo_id=colecao.id,
        detalhe={
            "project_id": item.project_id,
            "motivo": motivo,
            "incluido_por": item.added_by_user_id,
        },
    )
