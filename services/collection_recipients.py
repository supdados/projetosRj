"""Em que pé está cada convite de uma coleção (modal Compartilhar do dono).

``status_dos_shares`` lê em LOTE, sem N+1: status por pessoa
(``pendente|aceito|recusado|saiu|legado``), agregados do share de órgão e
quantos itens a poda tiraria se o share fosse revogado. O card do índice NÃO
lista destinatários (saiu da tela); a flag ``compartilhada`` dele vem de
``collection_shares.collection_ids_com_share``, em 1 query.

E a busca de quem PODE receber (``buscar_pessoas_para_compartilhar``, rota
``GET /api/colecoes/destinatarios``).

O status de cada pessoa vem de ``collection_access.status_do_destinatario`` —
a mesma regra que decide se o share concede acesso.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, TypedDict

from models import (
    STATUS_RESPOSTA_ACEITO,
    STATUS_RESPOSTA_RECUSADO,
    STATUS_RESPOSTA_SAIU,
    ProjectCollection,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    User,
    UserOrgao,
    db,
)
from services.collection_access import (
    STATUS_LEGADO,
    STATUS_PENDENTE,
    status_do_destinatario,
)
from services.collection_pruning import PrevisaoDaPoda, prever_poda

LIMITE_BUSCA_DESTINATARIOS = 20

_RespostasPorShare = dict[int, dict[int, str]]
_MembrosPorOrgao = dict[int, set[int]]


class ResumoDoOrgao(TypedDict):
    """Agregado das pessoas lotadas no órgão do share (``aceitos`` inclui legado)."""

    membros: int
    aceitos: int
    pendentes: int
    recusados: int
    sairam: int


class StatusDoShare(TypedDict):
    """Status de UM share para o modal do dono.

    ``status`` só em share de pessoa; ``resumo`` só em share de órgão.
    """

    status: str | None
    resumo: ResumoDoOrgao | None
    itens_incluidos: int


def status_dos_shares(
    colecao: ProjectCollection,
    shares: Iterable[ProjectCollectionShare],
    *,
    previsao: PrevisaoDaPoda | None = None,
) -> dict[int, StatusDoShare]:
    """``{share_id: StatusDoShare}`` dos shares da coleção (modal do dono).

    ``previsao`` (de ``prever_poda`` com os MESMOS shares) evita recontar quando
    a rota também precisa dos órfãos. Exemplo:
    ``status_dos_shares(colecao, listar_shares(colecao))[share.id]``.
    """
    shares = list(shares)
    respostas = _respostas_por_share([share.id for share in shares])
    membros = _membros_por_orgao({s.orgao_id for s in shares if s.orgao_id})
    itens = (previsao or prever_poda(colecao, shares)).por_share
    dono_id = colecao.owner_user_id
    return {
        share.id: StatusDoShare(
            status=_status_da_pessoa(share, respostas) if share.user_id else None,
            resumo=(
                None
                if share.user_id
                else _resumo_do_orgao(share, respostas, membros, dono_id)
            ),
            itens_incluidos=itens.get(share.id, 0),
        )
        for share in shares
    }


def buscar_pessoas_para_compartilhar(
    termo: str, *, ator: User, limite: int = LIMITE_BUSCA_DESTINATARIOS
) -> list[User]:
    """Pessoas ATIVAS cujo NOME contém ``termo`` (busca do modal de compartilhar).

    Decisão 4 da spec: aberta a qualquer logado, sem o gate de gestor. Casa só
    pelo nome — ``username`` pode ser o CPF (``routes/auth.py`` liga Gov.br por
    username = CPF), e buscar por ele deixaria qualquer servidor sondar CPFs.
    Exclui o próprio ator. Exemplo:
    ``buscar_pessoas_para_compartilhar("mar", ator=g.user)``.
    """
    padrao = f"%{_escapar_like(termo)}%"
    return (
        User.query.filter(
            User.deleted_at.is_(None),
            User.id != ator.id,
            User.name.ilike(padrao, escape="\\"),
        )
        .order_by(User.name, User.id)
        .limit(limite)
        .all()
    )


def _escapar_like(termo: str) -> str:
    # "%" ou "_" digitados casariam qualquer nome e virariam dump do diretório.
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _status_da_pessoa(
    share: ProjectCollectionShare, respostas: _RespostasPorShare
) -> str:
    resposta = respostas.get(share.id, {}).get(share.user_id)
    return status_do_destinatario(share.exige_aceite, resposta)


def _contagem_do_orgao(
    share: ProjectCollectionShare,
    respostas: _RespostasPorShare,
    membros: _MembrosPorOrgao,
    dono_id: int,
) -> Counter[str]:
    do_share = respostas.get(share.id, {})
    pessoas = membros.get(share.orgao_id, set()) - {dono_id}
    return Counter(
        status_do_destinatario(share.exige_aceite, do_share.get(pessoa))
        for pessoa in pessoas
    )


def _resumo_do_orgao(
    share: ProjectCollectionShare,
    respostas: _RespostasPorShare,
    membros: _MembrosPorOrgao,
    dono_id: int,
) -> ResumoDoOrgao:
    contagem = _contagem_do_orgao(share, respostas, membros, dono_id)
    return ResumoDoOrgao(
        membros=sum(contagem.values()),
        aceitos=contagem[STATUS_RESPOSTA_ACEITO] + contagem[STATUS_LEGADO],
        pendentes=contagem[STATUS_PENDENTE],
        recusados=contagem[STATUS_RESPOSTA_RECUSADO],
        sairam=contagem[STATUS_RESPOSTA_SAIU],
    )


def _respostas_por_share(share_ids: list[int]) -> _RespostasPorShare:
    if not share_ids:
        return {}
    resposta = ProjectCollectionShareResposta
    rows = db.session.query(
        resposta.share_id, resposta.user_id, resposta.status
    ).filter(resposta.share_id.in_(share_ids))
    por_share: _RespostasPorShare = {}
    for share_id, user_id, status in rows:
        por_share.setdefault(share_id, {})[user_id] = status
    return por_share


def _membros_por_orgao(orgao_ids: set[int]) -> _MembrosPorOrgao:
    """Ativos lotados no órgão EXATO (sem subárvore, como o share)."""
    if not orgao_ids:
        return {}
    rows = (
        db.session.query(UserOrgao.orgao_id, UserOrgao.user_id)
        .join(User, User.id == UserOrgao.user_id)
        .filter(UserOrgao.orgao_id.in_(orgao_ids), User.deleted_at.is_(None))
    )
    membros: _MembrosPorOrgao = {}
    for orgao_id, user_id in rows:
        membros.setdefault(orgao_id, set()).add(user_id)
    return membros
