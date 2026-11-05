"""Serialização da coleção COMPARTILHADA com aceite (card, shares, convites).

Módulo próprio porque ``routes/api/serializers.py`` já passa de 1000 linhas:
aqui ficam só os shapes que nasceram com o aceite e a curadoria — os antigos
(``serialize_colecao_resumo``, ``serialize_colecao_share``,
``serialize_project_collection_row``) continuam lá e são ESTENDIDOS por
composição, sem mudar nenhum campo existente.

Nenhuma função consulta banco: status, destinatários e contagens chegam prontos
de ``services.collection_shares`` (lote, sem N+1).
"""

from __future__ import annotations

from typing import Any, Optional

from models import ProjectCollection, ProjectCollectionShare, User
from services.collection_areas import AreaDaColecao
from services.collection_shares import (
    ConvitePendente,
    DestinatarioColecao,
    ResumoDoOrgao,
    StatusDoShare,
)
from time_utils import iso_utc

from .serializers import (
    serialize_colecao_resumo,
    serialize_colecao_share,
    serialize_project_collection_row,
)

# A linha "Compartilhada com" do card mostra no máximo 5 avatares + "+N".
LIMITE_DESTINATARIOS_CARD = 5


def serialize_colecao_card(
    colecao: ProjectCollection,
    rollup: dict[str, int],
    *,
    papel: str,
    destinatarios: list[DestinatarioColecao],
    areas: Optional[list[AreaDaColecao]] = None,
) -> dict[str, Any]:
    """``ColecaoResumo`` + ``destinatarios`` (até 5), ``destinatarios_total``
    e ``areas`` (pílula "N áreas" da capa, já ordenada).

    ``destinatarios`` já vem com a regra de quem vê aplicada
    (``destinatarios_por_colecao``): o dono recebe todos com status; quem
    participa recebe o dono e os outros aceitos. ``compartilhada`` deriva da
    mesma lista. ``areas`` vem de ``areas_por_colecao`` (só projetos
    visíveis). Exemplo:
    ``serialize_colecao_card(c, rollup, papel="dono", destinatarios=lista, areas=areas)``.
    """
    card = serialize_colecao_resumo(
        colecao, rollup, papel=papel, compartilhada=bool(destinatarios)
    )
    card["destinatarios"] = [
        serialize_destinatario_colecao(destinatario)
        for destinatario in destinatarios[:LIMITE_DESTINATARIOS_CARD]
    ]
    card["destinatarios_total"] = len(destinatarios)
    card["areas"] = [
        {"sigla": area["sigla"], "projetos": int(area["projetos"])}
        for area in areas or []
    ]
    return card


def serialize_destinatario_colecao(destinatario: DestinatarioColecao) -> dict[str, Any]:
    """Uma entrada do card: ``{tipo, id, nome, sigla, papel, status}``.

    ``tipo`` é ``user|orgao``; ``status`` é ``dono|aceito|legado|pendente|
    recusado|saiu`` (só o dono recebe os três últimos).
    """
    return {
        "tipo": destinatario["tipo"],
        "id": destinatario["id"],
        "nome": destinatario["nome"],
        "sigla": destinatario["sigla"],
        "papel": destinatario["papel"],
        "status": destinatario["status"],
    }


def serialize_colecao_share_com_status(
    share: ProjectCollectionShare, status: StatusDoShare
) -> dict[str, Any]:
    """``Share`` do contrato + ``exige_aceite``, ``status``, ``resumo`` e
    ``itens_incluidos`` (modal do dono).

    ``status`` só em share de pessoa (``pendente|aceito|recusado|saiu|legado``);
    ``resumo`` só em share de órgão; ``itens_incluidos`` = projetos que saem da
    coleção se este share for revogado. Exemplo:
    ``serialize_colecao_share_com_status(share, status_dos_shares(c, [share])[share.id])``.
    """
    payload = serialize_colecao_share(share)
    payload["exige_aceite"] = bool(share.exige_aceite)
    payload["status"] = status["status"]
    payload["resumo"] = _serialize_resumo_do_orgao(status["resumo"])
    payload["itens_incluidos"] = int(status["itens_incluidos"])
    return payload


def _serialize_resumo_do_orgao(
    resumo: Optional[ResumoDoOrgao],
) -> Optional[dict[str, int]]:
    if resumo is None:
        return None
    return {
        "membros": int(resumo["membros"]),
        "aceitos": int(resumo["aceitos"]),
        "pendentes": int(resumo["pendentes"]),
        "recusados": int(resumo["recusados"]),
        "sairam": int(resumo["sairam"]),
    }


def serialize_convite_colecao(convite: ConvitePendente) -> dict[str, Any]:
    """Convite pendente: SÓ metadados da coleção (nenhum projeto ou contagem).

    ``id`` é o da COLEÇÃO — o convidado nunca recebe ``share_id`` (aceite e
    recusa resolvem por coleção × usuário logado). Exemplo:
    ``serialize_convite_colecao(convite_pendente(cid, g.user))``.
    """
    colecao = convite.colecao
    return {
        "id": colecao.id,
        "nome": colecao.nome,
        "descricao": colecao.descricao,
        "icone": colecao.icone,
        "cor": colecao.cor,
        "owner": _pessoa_nome_ref(colecao.owner),
        "papel": convite.papel,
        "convidado_em": iso_utc(convite.convidado_em),
    }


def _pessoa_nome_ref(user: Optional[User]) -> Optional[dict[str, Any]]:
    # Mesmo shape ``{id, nome}`` do ``owner`` do card (serializers._pessoa_ref).
    if user is None:
        return None
    return {"id": user.id, "nome": user.name}


def serialize_colecao_projeto_row(row: dict[str, Any]) -> dict[str, Any]:
    """``ProjetoColecaoRow`` + ``adicionado_por`` (``{id, name}``|null) e
    ``pode_remover`` — ambos decididos no servidor (``colecao_project_rows``).

    ``adicionado_por`` nulo = item legado (conta como do dono).
    """
    payload = serialize_project_collection_row(row)
    incluidor = row.get("adicionado_por")
    payload["adicionado_por"] = (
        None
        if incluidor is None
        else {"id": incluidor["id"], "name": incluidor["name"]}
    )
    payload["pode_remover"] = bool(row.get("pode_remover"))
    return payload


def serialize_pessoa_destinavel(user: User, sigla: Optional[str]) -> dict[str, Any]:
    """Resultado da busca de destinatários: ``{id, name, orgao_sigla}``.

    Sem ``username`` de propósito: pode ser o CPF da pessoa, e a busca é aberta
    a qualquer logado (decisão 4). Nunca CPF, hash ou vínculo Gov.br.
    """
    return {"id": user.id, "name": user.name, "orgao_sigla": sigla}
