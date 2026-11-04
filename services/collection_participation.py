"""Quem participa de qual coleção: papel por share válido e convites pendentes.

Consultas no nível da COLEÇÃO (não do projeto), todas montadas com as peças
SQL de ``services.collection_access`` — a regra de "share vale"/"share
pendente" nunca é reescrita aqui. Consumidores: ``papel_do_usuario`` e o
índice (``services.project_collections``), aceite/recusa/saída
(``services.collection_shares``), o filtro ``?colecao=``
(``routes/projects/list_filters.py``) e o filtro do sino.

O dono nunca aparece como participante da própria coleção
(``criterios_share_base`` exige ``owner != me``): o papel dele é "dono", à parte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import aliased, contains_eager

from models import (
    ProjectCollection,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    User,
    db,
)
from services.collection_access import (
    criterio_resposta_pendente,
    criterio_resposta_valida,
    criterios_share_base,
    juncao_resposta,
    lotacao_orgao_ids,
    papel_share_mais_alto,
)

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

RespostaOuNada = ProjectCollectionShareResposta | None


def _shares_alcancaveis(user: Any, colunas: list[Any], dono: Any, resposta: Any) -> Any:
    """Share × coleção × dono × MINHA resposta, já com alcance/dono vivo/custom."""
    user_id = int(user.id)
    share, colecao = ProjectCollectionShare, ProjectCollection
    lotacao = lotacao_orgao_ids(user)
    return (
        db.session.query(*colunas)
        .select_from(share)
        .join(colecao, colecao.id == share.collection_id)
        .join(dono, dono.id == colecao.owner_user_id)
        .outerjoin(resposta, juncao_resposta(share, resposta, user_id))
        .filter(*criterios_share_base(share, colecao, dono, user_id, lotacao))
    )


def _aliases() -> tuple[Any, Any]:
    return aliased(User), aliased(ProjectCollectionShareResposta)


def _no_subconjunto(query: Any, colecao_ids: Iterable[int] | None) -> Any:
    if colecao_ids is None:
        return query
    ids = [int(collection_id) for collection_id in colecao_ids]
    return query.filter(ProjectCollectionShare.collection_id.in_(ids))


def papeis_validos_por_colecao(
    user: Any, colecao_ids: Iterable[int] | None = None
) -> dict[int, str]:
    """``{collection_id: papel}`` pelos shares VÁLIDOS (o mais alto vence).

    Não inclui coleções do próprio usuário. Exemplo:
    ``papeis_validos_por_colecao(g.user, [colecao.id]).get(colecao.id)``.
    """
    dono, resposta = _aliases()
    share = ProjectCollectionShare
    query = _shares_alcancaveis(
        user, [share.collection_id, share.papel], dono, resposta
    ).filter(criterio_resposta_valida(share, resposta))
    papeis: dict[int, str] = {}
    for collection_id, papel in _no_subconjunto(query, colecao_ids):
        papeis[collection_id] = papel_share_mais_alto(papeis.get(collection_id), papel)
    return papeis


def shares_pendentes_do_usuario(
    user: Any, colecao_ids: Iterable[int] | None = None
) -> list[ProjectCollectionShare]:
    """Shares em que ``user`` tem convite PENDENTE (exige aceite, sem resposta).

    Exemplo: ``shares_pendentes_do_usuario(g.user, [colecao.id])``.
    """
    dono, resposta = _aliases()
    share = ProjectCollectionShare
    query = _shares_alcancaveis(user, [share], dono, resposta).filter(
        criterio_resposta_pendente(share, resposta)
    )
    return _no_subconjunto(query, colecao_ids).order_by(share.id).all()


def shares_validos_do_usuario(
    user: Any, colecao_ids: Iterable[int] | None = None
) -> list[ProjectCollectionShare]:
    """Shares que VALEM para ``user`` (aceito ou legado), em ordem de criação."""
    dono, resposta = _aliases()
    share = ProjectCollectionShare
    query = _shares_alcancaveis(user, [share], dono, resposta).filter(
        criterio_resposta_valida(share, resposta)
    )
    return _no_subconjunto(query, colecao_ids).order_by(share.id).all()


def shares_e_respostas_do_usuario(
    user: Any, colecao_id: int
) -> list[tuple[ProjectCollectionShare, RespostaOuNada]]:
    """Todo share da coleção que ALCANÇA ``user`` + a resposta dele (ou None).

    Base de "sair": a saída marca todos os shares que alcançam a pessoa, de
    qualquer status. Exemplo: ``shares_e_respostas_do_usuario(g.user, 3)``.
    """
    dono, resposta = _aliases()
    share = ProjectCollectionShare
    query = _shares_alcancaveis(user, [share, resposta], dono, resposta)
    return _no_subconjunto(query, [colecao_id]).order_by(share.id).all()


def colecoes_compartilhadas_validas(
    user: Any,
) -> list[tuple[ProjectCollection, str]]:
    """Coleções de terceiros com share VÁLIDO para mim; papel mais alto vence.

    Dono já carregado (``contains_eager``) para o card não fazer N+1; ordem
    ``updated_at`` desc, id desc. Convite pendente/recusado/saiu fica de fora.
    """
    dono, resposta = _aliases()
    share, colecao = ProjectCollectionShare, ProjectCollection
    rows = (
        _shares_alcancaveis(user, [colecao, share.papel], dono, resposta)
        .options(contains_eager(colecao.owner.of_type(dono)))
        .filter(criterio_resposta_valida(share, resposta))
        .order_by(colecao.updated_at.desc(), colecao.id.desc())
        .all()
    )
    por_id: dict[int, tuple[ProjectCollection, str]] = {}
    for item_colecao, papel in rows:
        anterior = por_id.get(item_colecao.id)
        if anterior is not None:
            papel = papel_share_mais_alto(anterior[1], papel)
        por_id[item_colecao.id] = (item_colecao, papel)
    return list(por_id.values())


def colecao_com_papel_criterion(colecao: Any, user: Any) -> "ColumnElement[bool]":
    """SQL de "``papel_do_usuario`` não é None" sobre a coleção ``colecao``.

    Dono OU share válido (dono vivo, custom), correlacionado à ``colecao`` da
    query externa. Uso no filtro ``?colecao=`` de ``list_filters.py``.
    """
    user_id = int(user.id)
    share = aliased(ProjectCollectionShare)
    dono, resposta = _aliases()
    lotacao = lotacao_orgao_ids(user)
    # O dono entra pelo WHERE, não por JOIN ... ON: o ON citaria a coleção da
    # query EXTERNA (correlação dentro de ON), que o SQLite aceita mas que não
    # é garantido em todo dialeto — no WHERE a correlação é portável.
    share_valido = (
        db.session.query(share.id)
        .select_from(share)
        .outerjoin(resposta, juncao_resposta(share, resposta, user_id))
        .filter(
            share.collection_id == colecao.id,
            dono.id == colecao.owner_user_id,
            *criterios_share_base(share, colecao, dono, user_id, lotacao),
            criterio_resposta_valida(share, resposta),
        )
        .correlate(colecao)
        .exists()
    )
    return or_(colecao.owner_user_id == user_id, share_valido)


def colecoes_visiveis_ou_convidadas(user: Any, colecao_ids: Iterable[int]) -> set[int]:
    """Ids (do subconjunto) em que ``user`` é dono, tem share válido OU convite.

    Filtro do sino: aviso de ``/colecoes/<id>`` só aparece para quem ainda
    alcança a coleção ou tem convite pendente nela. 3 queries fixas.
    """
    ids = {int(collection_id) for collection_id in colecao_ids}
    if not ids:
        return set()
    proprias = {
        collection_id
        for (collection_id,) in db.session.query(ProjectCollection.id).filter(
            ProjectCollection.id.in_(ids),
            ProjectCollection.owner_user_id == int(user.id),
        )
    }
    validas = set(papeis_validos_por_colecao(user, ids))
    pendentes = {
        share.collection_id for share in shares_pendentes_do_usuario(user, ids)
    }
    return proprias | validas | pendentes
