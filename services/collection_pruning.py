"""Poda dos itens de coleção cujo incluidor perdeu o papel editor.

Regra (spec): item incluído por NÃO-dono só permanece enquanto o incluidor tiver
papel ``editor`` EFETIVO (share aceito ou legado) na coleção. Revogar share,
sair, recusar e rebaixar editor→viewer chamam ``podar_itens_sem_editor`` na
MESMA transação; cada item removido entra na trilha como
``colecao_projeto_removido`` com ``detalhe.motivo``. Sem a poda, a exposição
feita por quem saiu continuaria valendo sem ninguém autorizado por trás dela.

Incluidor ÓRFÃO = já estava sem papel editor ANTES da mutação (desativado,
mudou de órgão, perdeu uma corrida): a poda o leva junto em qualquer mutação,
mas com motivo próprio (``incluidor_sem_papel``) e fora das contagens por share
— a trilha e os diálogos não atribuem ao ator o que ele não causou.

Custo constante em N shares e N incluidores (``prever_poda``): a validade de
cada share para cada incluidor é julgada em Python, com a regra de
``services.collection_access``, sobre linhas lidas em lote.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple

from sqlalchemy.orm import selectinload

from models import (
    PAPEL_SHARE_EDITOR,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    User,
    db,
)
from services.authorization import invalidate_collection_rank_cache
from services.collection_access import share_vale_para_usuario
from services.collection_audit import auditar_poda
from time_utils import utc_now

MOTIVO_PODA_REVOGADO = "share_revogado"
MOTIVO_PODA_SAIU = "participante_saiu"
MOTIVO_PODA_RECUSOU = "convite_recusado"
MOTIVO_PODA_REBAIXADO = "papel_rebaixado"
MOTIVO_PODA_INCLUIDOR_SEM_PAPEL = "incluidor_sem_papel"


class PrevisaoDaPoda(NamedTuple):
    """O que a poda tiraria hoje — base dos diálogos de revogar/rebaixar/sair.

    ``por_share``: itens que saem se AQUELE share for revogado ou rebaixado (de
    quem tem nele o ÚNICO editor efetivo). ``por_editor``: itens de cada
    incluidor que ainda é editor (o que sai se ele sair). ``orfaos``: itens de
    quem JÁ está sem papel editor — saem em qualquer próxima poda.
    """

    por_share: dict[int, int]
    por_editor: dict[int, int]
    orfaos: int


def podar_itens_sem_editor(
    colecao: ProjectCollection,
    *,
    ator: User,
    motivo: str,
    orfaos_antes: set[int],
) -> int:
    """Remove (auditado) os itens cujo incluidor não-dono está sem editor.

    ``orfaos_antes`` = ``incluidores_sem_editor(colecao)`` lido ANTES de mutar:
    os itens deles saem com ``incluidor_sem_papel``; os de quem perdeu o editor
    POR ESTA mutação, com ``motivo``. Devolve quantos saíram por causa da
    mutação (sem os órfãos). Exemplo: ``podar_itens_sem_editor(colecao,
    ator=g.user, motivo="share_revogado", orfaos_antes=orfaos)``.
    """
    db.session.flush()
    perdem = incluidores_sem_editor(colecao)
    if not perdem:
        return 0
    pela_mutacao = 0
    for item in _itens_dos_incluidores(colecao, perdem):
        orfao = item.added_by_user_id in orfaos_antes
        motivo_do_item = MOTIVO_PODA_INCLUIDOR_SEM_PAPEL if orfao else motivo
        auditar_poda(colecao, item, ator, motivo_do_item)
        db.session.delete(item)
        pela_mutacao += 0 if orfao else 1
    colecao.updated_at = utc_now()
    invalidate_collection_rank_cache()
    return pela_mutacao


def incluidores_sem_editor(colecao: ProjectCollection) -> set[int]:
    """Ids dos incluidores não-donos que hoje NÃO têm papel editor efetivo.

    Ler ANTES de mutar e passar a ``podar_itens_sem_editor`` como
    ``orfaos_antes``. Exemplo: ``orfaos = incluidores_sem_editor(colecao)``.
    """
    editores = _shares_editor_por_incluidor(colecao, set(_itens_por_incluidor(colecao)))
    return {user_id for user_id, shares in editores.items() if not shares}


def prever_poda(
    colecao: ProjectCollection, shares: Iterable[ProjectCollectionShare] = ()
) -> PrevisaoDaPoda:
    """Contagens da poda para os ``shares`` dados, em número FIXO de queries.

    Pessoa + órgão: quem segue editor por outro share não conta no share
    revogado. Exemplo: ``prever_poda(colecao, listar_shares(colecao)).orfaos``.
    """
    contagem = _itens_por_incluidor(colecao)
    editores = _shares_editor_por_incluidor(colecao, set(contagem))
    por_editor = {uid: total for uid, total in contagem.items() if editores[uid]}
    return PrevisaoDaPoda(
        por_share={
            share.id: sum(
                total
                for uid, total in por_editor.items()
                if editores[uid] == {share.id}
            )
            for share in shares
        },
        por_editor=por_editor,
        orfaos=sum(total for uid, total in contagem.items() if not editores[uid]),
    )


def itens_que_saem_por_share(
    colecao: ProjectCollection, shares: Iterable[ProjectCollectionShare]
) -> dict[int, int]:
    """``{share_id: n}``: itens que a poda tiraria se AQUELE share fosse revogado
    (sem os órfãos, que já saem em qualquer poda — ver ``prever_poda``)."""
    return prever_poda(colecao, shares).por_share


def itens_incluidos_por(colecao: ProjectCollection, user_id: int) -> int:
    """Quantos itens ``user_id`` incluiu (todos, inclusive órfãos)."""
    return ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, added_by_user_id=user_id
    ).count()


def _itens_dos_incluidores(
    colecao: ProjectCollection, incluidores: set[int]
) -> list[ProjectCollectionItem]:
    return (
        ProjectCollectionItem.query.filter(
            ProjectCollectionItem.collection_id == colecao.id,
            ProjectCollectionItem.added_by_user_id.in_(incluidores),
        )
        .order_by(ProjectCollectionItem.id)
        .all()
    )


def _itens_por_incluidor(colecao: ProjectCollection) -> dict[int, int]:
    rows = (
        db.session.query(
            ProjectCollectionItem.added_by_user_id,
            db.func.count(ProjectCollectionItem.id),
        )
        .filter(
            ProjectCollectionItem.collection_id == colecao.id,
            ProjectCollectionItem.added_by_user_id.isnot(None),
            ProjectCollectionItem.added_by_user_id != colecao.owner_user_id,
        )
        .group_by(ProjectCollectionItem.added_by_user_id)
        .all()
    )
    return {user_id: int(total) for user_id, total in rows}


def _shares_editor_por_incluidor(
    colecao: ProjectCollection, incluidores: set[int]
) -> dict[int, set[int]]:
    """``{user_id: {share_id editor válido}}``; vazio = sem papel editor.

    Incluidor removido (soft-delete) nunca é editor. Até 5 queries, quaisquer
    que sejam os números de shares e de incluidores (antes: 2 por incluidor).
    """
    editores: dict[int, set[int]] = {user_id: set() for user_id in incluidores}
    shares = _shares_editor(colecao) if incluidores else []
    if not shares:
        return editores
    dono = db.session.get(User, colecao.owner_user_id)
    dono_vivo = dono is not None and dono.deleted_at is None
    respostas = _status_das_respostas([share.id for share in shares], incluidores)
    for user in _incluidores_ativos(incluidores):
        editores[user.id] = {
            share.id
            for share in shares
            if share_vale_para_usuario(
                share,
                user,
                respostas.get((share.id, user.id)),
                colecao=colecao,
                dono_vivo=dono_vivo,
            )
        }
    return editores


def _shares_editor(colecao: ProjectCollection) -> list[ProjectCollectionShare]:
    return ProjectCollectionShare.query.filter_by(
        collection_id=colecao.id, papel=PAPEL_SHARE_EDITOR
    ).all()


def _incluidores_ativos(user_ids: set[int]) -> list[User]:
    # selectinload: ``share_alcanca_usuario`` lê ``user.orgaos`` (lotação).
    return (
        User.query.options(selectinload(User.orgaos))
        .filter(User.id.in_(user_ids), User.deleted_at.is_(None))
        .all()
    )


def _status_das_respostas(
    share_ids: list[int], user_ids: set[int]
) -> dict[tuple[int, int], str]:
    resposta = ProjectCollectionShareResposta
    rows = db.session.query(
        resposta.share_id, resposta.user_id, resposta.status
    ).filter(resposta.share_id.in_(share_ids), resposta.user_id.in_(user_ids))
    return {(share_id, user_id): status for share_id, user_id, status in rows}
