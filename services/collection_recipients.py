"""Quem recebeu cada coleção e em que pé está cada convite (card e modal).

Duas leituras em LOTE, sem N+1 (orçamento de ≤ 20 queries do índice em
``tests/routes/test_read_materialization.py``):

- ``status_dos_shares``: o modal do dono — status por pessoa
  (``pendente|aceito|recusado|saiu|legado``), agregados do share de órgão e
  quantos itens a poda tiraria se o share fosse revogado.
- ``destinatarios_por_colecao``: a linha "Compartilhada com" do card. O dono vê
  todos os destinatários com status; quem participa vê o dono e os OUTROS
  aceitos (pendente/recusado alheio não é da conta dele).

E a busca de quem PODE receber (``buscar_pessoas_para_compartilhar``, rota
``GET /api/colecoes/destinatarios``).

O status de cada pessoa vem de ``collection_access.status_do_destinatario`` —
a mesma regra que decide se o share concede acesso.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, TypedDict

from sqlalchemy.orm import joinedload

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
from services.collection_errors import PAPEL_COLECAO_DONO
from services.collection_pruning import PrevisaoDaPoda, prever_poda

STATUS_DONO = "dono"
TIPO_DESTINATARIO_USER = "user"
TIPO_DESTINATARIO_ORGAO = "orgao"
LIMITE_BUSCA_DESTINATARIOS = 20
_COM_ACESSO = (STATUS_RESPOSTA_ACEITO, STATUS_LEGADO)

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


class DestinatarioColecao(TypedDict):
    """Uma entrada da linha "Compartilhada com" do card."""

    tipo: str
    id: int
    nome: str
    sigla: str | None
    papel: str
    status: str


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


def destinatarios_por_colecao(
    colecoes: Iterable[ProjectCollection], viewer: User
) -> dict[int, list[DestinatarioColecao]]:
    """``{collection_id: [DestinatarioColecao]}`` do card, com a regra de quem vê.

    Recebe as coleções já carregadas (o dono das compartilhadas vem com
    ``contains_eager`` do índice). Até 3 queries, independente de N coleções.
    A rota corta a lista (ex.: 5 primeiros) e usa ``len`` como total.
    """
    colecoes = list(colecoes)
    shares = _shares_com_destino([colecao.id for colecao in colecoes])
    respostas = _respostas_por_share([share.id for share in shares])
    membros = _membros_por_orgao({s.orgao_id for s in shares if s.orgao_id})
    por_colecao: dict[int, list[DestinatarioColecao]] = {c.id: [] for c in colecoes}
    donos = {colecao.id: colecao.owner_user_id for colecao in colecoes}
    for share in shares:
        dono_id = donos[share.collection_id]
        por_colecao[share.collection_id].append(
            _destinatario(share, respostas, membros, dono_id)
        )
    return {
        colecao.id: _visiveis_para(colecao, por_colecao[colecao.id], viewer)
        for colecao in colecoes
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


def _visiveis_para(
    colecao: ProjectCollection,
    destinatarios: list[DestinatarioColecao],
    viewer: User,
) -> list[DestinatarioColecao]:
    if viewer.id == colecao.owner_user_id:
        return destinatarios
    outros_aceitos = [
        destinatario
        for destinatario in destinatarios
        if destinatario["status"] in _COM_ACESSO
        and not (
            destinatario["tipo"] == TIPO_DESTINATARIO_USER
            and destinatario["id"] == viewer.id
        )
    ]
    return [_entrada_do_dono(colecao), *outros_aceitos]


def _entrada_do_dono(colecao: ProjectCollection) -> DestinatarioColecao:
    dono = colecao.owner
    return DestinatarioColecao(
        tipo=TIPO_DESTINATARIO_USER,
        id=colecao.owner_user_id,
        nome=dono.name if dono is not None else "",
        sigla=None,
        papel=PAPEL_COLECAO_DONO,
        status=STATUS_DONO,
    )


def _destinatario(
    share: ProjectCollectionShare,
    respostas: _RespostasPorShare,
    membros: _MembrosPorOrgao,
    dono_id: int,
) -> DestinatarioColecao:
    if share.user_id is not None:
        return DestinatarioColecao(
            tipo=TIPO_DESTINATARIO_USER,
            id=share.user_id,
            nome=share.user.name if share.user is not None else "",
            sigla=None,
            papel=share.papel,
            status=_status_da_pessoa(share, respostas),
        )
    orgao = share.orgao
    return DestinatarioColecao(
        tipo=TIPO_DESTINATARIO_ORGAO,
        id=share.orgao_id,
        nome=orgao.nome if orgao is not None else "",
        sigla=orgao.sigla if orgao is not None else None,
        papel=share.papel,
        status=_status_do_orgao(share, respostas, membros, dono_id),
    )


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


def _status_do_orgao(
    share: ProjectCollectionShare,
    respostas: _RespostasPorShare,
    membros: _MembrosPorOrgao,
    dono_id: int,
) -> str:
    """Um status para o selo do órgão: alguém com acesso > pendente > recusas."""
    contagem = _contagem_do_orgao(share, respostas, membros, dono_id)
    if contagem[STATUS_RESPOSTA_ACEITO] or contagem[STATUS_LEGADO]:
        return STATUS_RESPOSTA_ACEITO if share.exige_aceite else STATUS_LEGADO
    for status in (STATUS_PENDENTE, STATUS_RESPOSTA_RECUSADO, STATUS_RESPOSTA_SAIU):
        if contagem[status]:
            return status
    # Órgão sem ninguém lotado: o convite fica esperando quem entrar.
    return STATUS_PENDENTE if share.exige_aceite else STATUS_LEGADO


def _shares_com_destino(colecao_ids: list[int]) -> list[ProjectCollectionShare]:
    if not colecao_ids:
        return []
    return (
        ProjectCollectionShare.query.options(
            joinedload(ProjectCollectionShare.user),
            joinedload(ProjectCollectionShare.orgao),
        )
        .filter(ProjectCollectionShare.collection_id.in_(colecao_ids))
        .order_by(ProjectCollectionShare.id)
        .all()
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
