"""Predicado ÚNICO de acesso via coleção compartilhada (share × resposta × item).

Toda pergunta "este share vale para mim?" e "este item me concede rank?" passa
por aqui — rank map (``services.authorization``), EXISTS das listagens, papel
na coleção (``services.project_collections.papel_do_usuario``), índice de
compartilhadas, convites pendentes, filtro ``?colecao=`` e notificações. Antes a
regra vivia copiada em três lugares e divergir uma cópia era vazamento.

A regra (``spec-colecao-compartilhada``)::

    alcanca(share, me)       := share.user_id == me OR share.orgao_id ∈ lotação exata
    share_vale(share, me)    := alcanca AND dono vivo AND coleção custom AND dono != me
                                AND resposta(me) == aceito
                                    OR (sem resposta AND NOT share.exige_aceite)
    share_pendente(share,me) := alcanca AND dono vivo AND custom AND dono != me
                                AND share.exige_aceite AND sem resposta
    teto(item)               := EDITOR se rank_teto IS NULL senão min(rank_teto, EDITOR)
    rank_via_item(item, me)  := max(
        min(PAPEL_RANK[share.papel], teto)  por share válido, se incluidor != me,
        min(LEITOR, teto)                   se me == dono e incluidor != me)
    incluidor(item)          := COALESCE(item.added_by_user_id, coleção.owner)

"Ninguém deriva acesso de item que ele mesmo incluiu" generaliza o antigo
anti-auto-escalonamento do dono. UNIQUE(share_id, user_id) garante no máximo
uma resposta por pessoa, então "resposta == aceito OR (sem resposta AND
legado)" equivale ao par NOT EXISTS(recusado|saiu) / EXISTS(aceito) da spec —
e falha FECHADO para qualquer status desconhecido.

As consultas de papel/convite por coleção (índice, ``papel_do_usuario``,
convites pendentes, ``?colecao=``, sino) moram em
``services.collection_participation`` e são montadas SÓ com as peças SQL
públicas daqui (``criterios_share_base``, ``criterio_resposta_valida``...).

Duas formas da MESMA regra, cobertas por teste de equivalência
(``tests/test_collection_access_unit.py``): SQL (EXISTS correlacionado, para
listagens) e Python (``rank_via_share``/``rank_via_dono`` sobre linhas
candidatas, para o rank map por request). ``share_vale_para_usuario`` julga a
validade de N pessoas em lote para a poda (equivalência com o SQL em
``tests/test_collection_pruning_unit.py``). Sem checagem de admin aqui: o
bypass do admin é de ``services.authorization`` (grep-gate F0-6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import aliased

from models import (
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    STATUS_RESPOSTA_ACEITO,
    TIPO_COLECAO_CUSTOM,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    User,
    db,
)
from services.access_ranks import PAPEL_EDITOR, PAPEL_LEITOR, PAPEL_RANK
from services.collection_errors import PAPEL_COLECAO_DONO

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

STATUS_LEGADO = "legado"
STATUS_PENDENTE = "pendente"

RANK_LEITOR: int = PAPEL_RANK[PAPEL_LEITOR]
RANK_EDITOR: int = PAPEL_RANK[PAPEL_EDITOR]


class CandidatoViaShare(NamedTuple):
    """Linha item × share que alcança o usuário, ainda sem julgar validade."""

    project_id: int
    rank_teto: int | None
    added_by_user_id: int | None
    owner_user_id: int
    tipo: str
    dono_vivo: bool
    papel: str
    exige_aceite: bool
    status_resposta: str | None


class CandidatoDoDono(NamedTuple):
    """Item de coleção do PRÓPRIO usuário (ramo "dono vê o que outros incluíram")."""

    project_id: int
    rank_teto: int | None
    added_by_user_id: int | None
    owner_user_id: int
    tipo: str


# ── Regra em Python (puras, sem banco) ───────────────────────────────────────


def lotacao_orgao_ids(user: Any) -> set[int]:
    """Órgãos EXATOS de lotação (linhas de ``user_orgao``), sem subárvore.

    Exemplo: ``share.orgao_id in lotacao_orgao_ids(g.user)``.
    """
    return {vinculo.orgao_id for vinculo in getattr(user, "orgaos", None) or []}


def share_alcanca_usuario(share: Any, user: Any) -> bool:
    """Python de ``alcanca``: share na pessoa OU no órgão exato de lotação.

    Exemplo: ``share_alcanca_usuario(share, g.user)``.
    """
    if share.user_id is not None:
        return share.user_id == getattr(user, "id", None)
    return share.orgao_id in lotacao_orgao_ids(user)


def share_vale(exige_aceite: bool, status_resposta: str | None) -> bool:
    """Parte "resposta" de ``share_vale``: aceito, ou legado sem resposta.

    Exemplo: ``share_vale(False, None) is True`` (legado);
    ``share_vale(True, None) is False`` (pendente).
    """
    if status_resposta == STATUS_RESPOSTA_ACEITO:
        return True
    return status_resposta is None and not exige_aceite


def share_vale_para_usuario(
    share: Any,
    user: Any,
    status_resposta: str | None,
    *,
    colecao: Any,
    dono_vivo: bool,
) -> bool:
    """Python de ``share_vale`` INTEIRO (alcance + dono vivo + custom + dono !=
    me + resposta) para quem já tem as linhas em mãos — ex.: avaliar N pessoas
    de uma vez sem N consultas. Mesma regra de ``criterios_share_base`` +
    ``criterio_resposta_valida``. Exemplo:
    ``share_vale_para_usuario(share, user, None, colecao=c, dono_vivo=True)``.
    """
    if not dono_vivo or colecao.tipo != TIPO_COLECAO_CUSTOM:
        return False
    if colecao.owner_user_id == getattr(user, "id", None):
        return False
    if not share_alcanca_usuario(share, user):
        return False
    return share_vale(share.exige_aceite, status_resposta)


def share_pendente(exige_aceite: bool, status_resposta: str | None) -> bool:
    """Parte "resposta" de ``share_pendente``: exige aceite e ninguém respondeu."""
    return bool(exige_aceite) and status_resposta is None


def status_do_destinatario(exige_aceite: bool, status_resposta: str | None) -> str:
    """``pendente|aceito|recusado|saiu|legado`` de UMA pessoa num share.

    Exemplo: ``status_do_destinatario(True, None) == "pendente"``.
    """
    if status_resposta is not None:
        return status_resposta
    return STATUS_PENDENTE if exige_aceite else STATUS_LEGADO


def papel_share_rank(papel: str) -> int:
    """Rank que o PAPEL do share concede (antes do teto do item).

    Papel fora da whitelist (linha adulterada) cai em leitor, nunca acima.
    """
    if papel == PAPEL_SHARE_EDITOR:
        return RANK_EDITOR
    return RANK_LEITOR


def papel_share_mais_alto(papel_a: str | None, papel_b: str | None) -> str | None:
    """Editor vence viewer; ``None`` é neutro. Ex.: ``("viewer", "editor") → "editor"``."""
    if PAPEL_SHARE_EDITOR in (papel_a, papel_b):
        return PAPEL_SHARE_EDITOR
    if PAPEL_SHARE_VIEWER in (papel_a, papel_b):
        return PAPEL_SHARE_VIEWER
    return None


def teto_do_item(rank_teto: int | None) -> int:
    """Teto de rank que o item concede: NULL (legado) = editor; nunca > editor."""
    if rank_teto is None:
        return RANK_EDITOR
    return max(0, min(int(rank_teto), RANK_EDITOR))


def rank_teto_de_inclusao(rank_de_area: int) -> int:
    """Valor gravado em ``item.rank_teto``: rank de área do incluidor, até editor.

    Exemplo: admin (100) grava 20; leitor de área grava 10; sem área grava 0.
    """
    return max(0, min(int(rank_de_area), RANK_EDITOR))


def incluidor_do_item(added_by_user_id: int | None, owner_user_id: int) -> int:
    """Quem incluiu o item; linha legada (NULL) conta como do dono."""
    return owner_user_id if added_by_user_id is None else added_by_user_id


def rank_via_share(candidato: CandidatoViaShare, me: int) -> int:
    """Rank que UM par item×share concede a ``me`` (0 = nada).

    O chamador já filtrou ``alcanca``; aqui ficam dono vivo/custom/dono != me,
    validade da resposta, item próprio e teto.
    """
    if candidato.owner_user_id == me or not candidato.dono_vivo:
        return 0
    if candidato.tipo != TIPO_COLECAO_CUSTOM:
        return 0
    if not share_vale(candidato.exige_aceite, candidato.status_resposta):
        return 0
    if incluidor_do_item(candidato.added_by_user_id, candidato.owner_user_id) == me:
        return 0
    return min(papel_share_rank(candidato.papel), teto_do_item(candidato.rank_teto))


def rank_via_dono(candidato: CandidatoDoDono, me: int) -> int:
    """Leitura que o DONO deriva de item que OUTRA pessoa incluiu (0 = nada)."""
    if candidato.owner_user_id != me or candidato.tipo != TIPO_COLECAO_CUSTOM:
        return 0
    if incluidor_do_item(candidato.added_by_user_id, candidato.owner_user_id) == me:
        return 0
    return min(RANK_LEITOR, teto_do_item(candidato.rank_teto))


def pode_remover_item(papel: str | None, added_by_user_id: int | None, me: int) -> bool:
    """Dono remove qualquer item; editor só o que ELE incluiu (legado é do dono).

    ``papel`` é o de ``papel_do_usuario`` (``"dono"|"editor"|"viewer"|None``).
    """
    if papel == PAPEL_COLECAO_DONO:
        return True
    if papel != PAPEL_SHARE_EDITOR:
        return False
    return added_by_user_id is not None and added_by_user_id == me


# ── Regra em SQL (mesma semântica; aliases evitam colisão com a query externa) ─
#
# Peças públicas para ``services.collection_participation`` montar as consultas
# de papel/convite SEM reescrever a regra. Toda consulta que as usa precisa
# juntar share → coleção → dono e fazer OUTER JOIN da resposta com
# ``juncao_resposta`` (no máximo 1 linha por share, pela UNIQUE).


def criterio_alcance(share: Any, user_id: int, lotacao: set[int]) -> Any:
    """SQL de ``alcanca``: share na pessoa OU no órgão exato de lotação."""
    destinos = [share.user_id == user_id]
    if lotacao:
        destinos.append(share.orgao_id.in_(lotacao))
    return or_(*destinos)


def criterios_share_base(
    share: Any, colecao: Any, dono: Any, user_id: int, lotacao: set[int]
) -> list[Any]:
    """Alcance + dono vivo + custom + não é o dono — comum a válido e pendente."""
    return [
        criterio_alcance(share, user_id, lotacao),
        dono.deleted_at.is_(None),
        colecao.tipo == TIPO_COLECAO_CUSTOM,
        colecao.owner_user_id != user_id,
    ]


def criterio_resposta_valida(share: Any, resposta: Any) -> Any:
    """SQL de ``share_vale``: aceito, ou sem resposta em share legado."""
    return or_(
        resposta.status == STATUS_RESPOSTA_ACEITO,
        and_(resposta.id.is_(None), share.exige_aceite.is_(False)),
    )


def criterio_resposta_pendente(share: Any, resposta: Any) -> Any:
    """SQL de ``share_pendente``: exige aceite e ninguém respondeu."""
    return and_(share.exige_aceite.is_(True), resposta.id.is_(None))


def juncao_resposta(share: Any, resposta: Any, user_id: int) -> Any:
    """ON do OUTER JOIN da resposta de ``user_id`` àquele share."""
    return and_(resposta.share_id == share.id, resposta.user_id == user_id)


def criterios_item_concede(item: Any, colecao: Any, user_id: int) -> list[Any]:
    """Item não incluído por mim E com teto > 0 (``min(x, 0) == 0``)."""
    incluidor = func.coalesce(item.added_by_user_id, colecao.owner_user_id)
    return [
        incluidor != user_id,
        or_(item.rank_teto.is_(None), item.rank_teto > 0),
    ]


def _exists_item_via_share(user_id: int, lotacao: set[int]) -> Any:
    item = aliased(ProjectCollectionItem)
    share = aliased(ProjectCollectionShare)
    colecao = aliased(ProjectCollection)
    dono = aliased(User)
    resposta = aliased(ProjectCollectionShareResposta)
    return (
        db.session.query(item.id)
        .join(share, share.collection_id == item.collection_id)
        .join(colecao, colecao.id == item.collection_id)
        .join(dono, dono.id == colecao.owner_user_id)
        .outerjoin(resposta, juncao_resposta(share, resposta, user_id))
        .filter(
            item.project_id == Project.id,
            *criterios_share_base(share, colecao, dono, user_id, lotacao),
            criterio_resposta_valida(share, resposta),
            *criterios_item_concede(item, colecao, user_id),
        )
        .correlate(Project)
        .exists()
    )


def _exists_item_via_dono(user_id: int) -> Any:
    item = aliased(ProjectCollectionItem)
    colecao = aliased(ProjectCollection)
    return (
        db.session.query(item.id)
        .join(colecao, colecao.id == item.collection_id)
        .filter(
            item.project_id == Project.id,
            colecao.owner_user_id == user_id,
            colecao.tipo == TIPO_COLECAO_CUSTOM,
            *criterios_item_concede(item, colecao, user_id),
        )
        .correlate(Project)
        .exists()
    )


def visibilidade_via_colecao_criterion(user: Any) -> "ColumnElement[bool]":
    """EXISTS correlacionado em ``Project.id``: algum item me concede rank > 0.

    Equivalente SQL de ``construir_rank_map_de_colecoes`` (``pid`` no mapa ⇔
    EXISTS verdadeiro). Uso: ``query.filter(visibilidade_via_colecao_criterion(u))``
    em query que já envolve ``Project``.
    """
    user_id = int(user.id)
    return or_(
        _exists_item_via_share(user_id, lotacao_orgao_ids(user)),
        _exists_item_via_dono(user_id),
    )


# ── Rank map (Python sobre candidatos) ───────────────────────────────────────


def _candidatos_via_share(user_id: int, lotacao: set[int]) -> list[CandidatoViaShare]:
    item, share, colecao = (
        ProjectCollectionItem,
        ProjectCollectionShare,
        ProjectCollection,
    )
    dono = aliased(User)
    resposta = aliased(ProjectCollectionShareResposta)
    rows = (
        db.session.query(
            item.project_id,
            item.rank_teto,
            item.added_by_user_id,
            colecao.owner_user_id,
            colecao.tipo,
            dono.deleted_at.is_(None),
            share.papel,
            share.exige_aceite,
            resposta.status,
        )
        .select_from(item)
        .join(share, share.collection_id == item.collection_id)
        .join(colecao, colecao.id == item.collection_id)
        .join(dono, dono.id == colecao.owner_user_id)
        .outerjoin(resposta, juncao_resposta(share, resposta, user_id))
        # Só o ALCANCE filtra em SQL: a validade é julgada em Python, para que o
        # teste de equivalência compare as duas formas da regra de verdade.
        .filter(criterio_alcance(share, user_id, lotacao))
        .all()
    )
    return [CandidatoViaShare(*row) for row in rows]


def _candidatos_do_dono(user_id: int) -> list[CandidatoDoDono]:
    item, colecao = ProjectCollectionItem, ProjectCollection
    rows = (
        db.session.query(
            item.project_id,
            item.rank_teto,
            item.added_by_user_id,
            colecao.owner_user_id,
            colecao.tipo,
        )
        .join(colecao, colecao.id == item.collection_id)
        # Pré-filtro de volume (Favoritos e itens próprios nunca concedem); a
        # regra completa é reavaliada em ``rank_via_dono``.
        .filter(
            colecao.owner_user_id == user_id,
            item.added_by_user_id.isnot(None),
            item.added_by_user_id != user_id,
        )
        .all()
    )
    return [CandidatoDoDono(*row) for row in rows]


def _acumular_rank(rank_map: dict[int, int], project_id: int, rank: int) -> None:
    if rank > 0:
        rank_map[project_id] = max(rank_map.get(project_id, 0), rank)


def construir_rank_map_de_colecoes(user: Any) -> dict[int, int]:
    """``{project_id: rank}`` derivado de coleções, SEM cache (2 queries).

    O cache por request e o curto-circuito de usuário removido ficam em
    ``services.authorization.get_collection_project_rank_map``. Tabela ausente
    (janela de deploy antes da migração) devolve ``{}``: falha fechada.
    """
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return {}
    try:
        # Savepoint: em Postgres a query falhada invalida a transação; rollback
        # global aqui descartaria mutações pendentes do request.
        with db.session.begin_nested():
            via_share = _candidatos_via_share(user_id, lotacao_orgao_ids(user))
            do_dono = _candidatos_do_dono(user_id)
    except (OperationalError, ProgrammingError):
        return {}
    rank_map: dict[int, int] = {}
    for candidato in via_share:
        _acumular_rank(
            rank_map, candidato.project_id, rank_via_share(candidato, user_id)
        )
    for candidato in do_dono:
        _acumular_rank(
            rank_map, candidato.project_id, rank_via_dono(candidato, user_id)
        )
    return rank_map
