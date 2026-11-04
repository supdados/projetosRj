"""Convite de coleção do lado do DESTINATÁRIO: listar, aceitar, recusar, sair.

Tudo resolvido por (coleção, usuário logado) — nunca por ``share_id`` do
cliente. Aceitar/recusar resolvem TODOS os shares pendentes da coleção que
alcançam a pessoa (pessoal + órgão); sair marca ``saiu`` em todos os que a
alcançam e poda o que ela incluiu. Corrida, convite revogado ou já respondido
viram ``ConviteIndisponivel`` (404 idêntico na rota), nunca 500.

Não commita (padrão dos services de coleção); avisa o dono e audita.
"""

from __future__ import annotations

import datetime
from typing import NamedTuple

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from models import (
    STATUS_RESPOSTA_ACEITO,
    STATUS_RESPOSTA_RECUSADO,
    STATUS_RESPOSTA_SAIU,
    ProjectCollection,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    User,
    db,
)
from services.authorization import invalidate_collection_rank_cache
from services.collection_access import papel_share_mais_alto
from services.collection_audit import auditar_resposta
from services.collection_errors import ConviteIndisponivel
from services.collection_participation import (
    shares_e_respostas_do_usuario,
    shares_pendentes_do_usuario,
    shares_validos_do_usuario,
)
from services.collection_pruning import (
    MOTIVO_PODA_RECUSOU,
    MOTIVO_PODA_SAIU,
    incluidores_sem_editor,
    podar_itens_sem_editor,
)
from services.notifications import (
    notify_collection_invite_accepted,
    notify_collection_invite_declined,
    notify_collection_member_left,
)
from time_utils import utc_now

_Resposta = ProjectCollectionShareResposta


class ConvitePendente(NamedTuple):
    """Convite de UMA coleção para o usuário (papel mais alto entre os shares)."""

    colecao: ProjectCollection
    papel: str
    convidado_em: datetime.datetime | None


def convites_pendentes_de(user: User) -> list[ConvitePendente]:
    """Convites pendentes do usuário, mais recentes primeiro (2 queries).

    Só metadados: a coleção vem com o dono carregado, nunca projetos.
    Exemplo: ``[c.colecao.nome for c in convites_pendentes_de(g.user)]``.
    """
    return _agrupar_convites(shares_pendentes_do_usuario(user))


def convite_pendente(colecao_id: int, user: User) -> ConvitePendente | None:
    """Convite pendente de ``user`` naquela coleção; ``None`` → 404 idêntico."""
    convites = _agrupar_convites(shares_pendentes_do_usuario(user, [colecao_id]))
    return convites[0] if convites else None


def aceitar_convite(colecao_id: int, ator: User) -> ProjectCollection:
    """Aceita TODOS os shares pendentes da coleção que alcançam o ator.

    Corrida (duplo clique, revogação no meio) ou nada pendente →
    ``ConviteIndisponivel`` (404 limpo, nunca 500). Avisa o dono e audita.
    """
    colecao, pendentes = _colecao_e_pendentes(colecao_id, ator)
    _registrar_respostas(pendentes, ator, STATUS_RESPOSTA_ACEITO)
    auditar_resposta(colecao, ator, "colecao_convite_aceito", pendentes)
    notify_collection_invite_accepted(colecao, ator)
    invalidate_collection_rank_cache()
    return colecao


def recusar_convite(colecao_id: int, ator: User) -> ProjectCollection:
    """Recusa TODOS os shares pendentes da coleção que alcançam o ator."""
    colecao, pendentes = _colecao_e_pendentes(colecao_id, ator)
    orfaos = incluidores_sem_editor(colecao)
    _registrar_respostas(pendentes, ator, STATUS_RESPOSTA_RECUSADO)
    auditar_resposta(colecao, ator, "colecao_convite_recusado", pendentes)
    podar_itens_sem_editor(
        colecao, ator=ator, motivo=MOTIVO_PODA_RECUSOU, orfaos_antes=orfaos
    )
    notify_collection_invite_declined(colecao, ator)
    invalidate_collection_rank_cache()
    return colecao


def sair_da_colecao(colecao_id: int, ator: User) -> int:
    """Sai da coleção (quem tem share válido); devolve quantos itens DELE saíram.

    Marca ``saiu`` em todo share que alcança o ator (inclusive pendente) e poda
    os itens que ele incluiu (os de incluidores já órfãos saem junto, fora da
    contagem). Sem participação válida → 404. Avisa o dono.
    """
    colecao = db.session.get(ProjectCollection, colecao_id)
    if colecao is None or not shares_validos_do_usuario(ator, [colecao_id]):
        raise ConviteIndisponivel(
            f"usuário id={ator.id} não participa da coleção id={colecao_id}"
        )
    orfaos = incluidores_sem_editor(colecao)
    pares = shares_e_respostas_do_usuario(ator, colecao_id)
    _marcar_saida(pares, ator)
    podados = podar_itens_sem_editor(
        colecao, ator=ator, motivo=MOTIVO_PODA_SAIU, orfaos_antes=orfaos
    )
    shares = [share for share, _ in pares]
    auditar_resposta(
        colecao, ator, "colecao_participante_saiu", shares, itens_podados=podados
    )
    notify_collection_member_left(colecao, ator)
    invalidate_collection_rank_cache()
    return podados


def _colecao_e_pendentes(
    colecao_id: int, ator: User
) -> tuple[ProjectCollection, list[ProjectCollectionShare]]:
    colecao = db.session.get(ProjectCollection, colecao_id)
    pendentes = shares_pendentes_do_usuario(ator, [colecao_id]) if colecao else []
    if colecao is None or not pendentes:
        raise ConviteIndisponivel(
            f"convite não está mais disponível: coleção id={colecao_id}"
        )
    return colecao, pendentes


def _registrar_respostas(
    shares: list[ProjectCollectionShare], ator: User, status: str
) -> None:
    """Transição condicional: a UNIQUE(share_id, user_id) só deixa responder 1x.

    Sem savepoint de propósito: nada continua depois de uma falha (a rota faz
    rollback) e, no pysqlite, o RELEASE de um savepoint aberto antes de qualquer
    escrita COMMITA — a releitura de ``_exigir_shares_vivos`` não desfaria mais.
    """
    # Ids lidos ANTES do flush: depois de uma falha a sessão não recarrega nada.
    share_ids = [share.id for share in shares]
    ator_id = ator.id
    for share_id in share_ids:
        db.session.add(_Resposta(share_id=share_id, user_id=ator_id, status=status))
    try:
        db.session.flush()
    except IntegrityError as exc:
        raise ConviteIndisponivel(
            f"convite já respondido ou revogado: shares={share_ids}"
        ) from exc
    _exigir_shares_vivos(set(share_ids))


def _exigir_shares_vivos(ids: set[int]) -> None:
    # MySQL barra pela FK; SQLite sem PRAGMA foreign_keys aceitaria resposta
    # de share revogado no meio do request — a releitura fecha a corrida.
    vivos = {
        share_id
        for (share_id,) in db.session.query(ProjectCollectionShare.id).filter(
            ProjectCollectionShare.id.in_(ids)
        )
    }
    if vivos != ids:
        raise ConviteIndisponivel(
            f"convite revogado durante a resposta: shares={sorted(ids - vivos)}"
        )


def _marcar_saida(
    pares: list[tuple[ProjectCollectionShare, ProjectCollectionShareResposta | None]],
    ator: User,
) -> None:
    """``saiu`` em todo share que alcança o ator (sem savepoint: ver acima).

    Sem resposta → INSERT (a UNIQUE barra o duplo); ``aceito`` → UPDATE
    condicional. Os shares tocados são relidos no fim, como no aceite.
    """
    agora = utc_now()
    # Ids lidos ANTES de qualquer flush: depois de uma falha nada recarrega.
    sem_resposta = [share.id for share, resposta in pares if resposta is None]
    aceitas = [
        (share.id, resposta.id)
        for share, resposta in pares
        if resposta is not None and resposta.status == STATUS_RESPOSTA_ACEITO
    ]
    _inserir_saidas(sem_resposta, ator.id, agora)
    for _share_id, resposta_id in aceitas:
        _trocar_aceito_por_saiu(resposta_id, agora)
    _exigir_shares_vivos({*sem_resposta, *(share_id for share_id, _ in aceitas)})


def _inserir_saidas(
    share_ids: list[int], ator_id: int, agora: datetime.datetime
) -> None:
    for share_id in share_ids:
        db.session.add(
            _Resposta(
                share_id=share_id,
                user_id=ator_id,
                status=STATUS_RESPOSTA_SAIU,
                respondido_em=agora,
            )
        )
    try:
        db.session.flush()
    except IntegrityError as exc:
        raise ConviteIndisponivel(
            f"saída concorrente da coleção pelo usuário id={ator_id}"
        ) from exc


def _trocar_aceito_por_saiu(resposta_id: int, agora: datetime.datetime) -> None:
    """UPDATE ... WHERE status='aceito': transição condicional, nunca às cegas.

    A atribuição ORM fazia UPDATE só pela PK: com a resposta apagada por uma
    revogação concorrente virava ``StaleDataError`` (500), e um segundo "sair"
    concorrente passava de novo (aviso ao dono e auditoria duplicados).
    """
    resultado = db.session.execute(
        update(_Resposta)
        .where(_Resposta.id == resposta_id, _Resposta.status == STATUS_RESPOSTA_ACEITO)
        .values(status=STATUS_RESPOSTA_SAIU, respondido_em=agora)
    )
    if resultado.rowcount != 1:
        raise ConviteIndisponivel(
            f"saída concorrente: resposta id={resposta_id} não está mais "
            f"'{STATUS_RESPOSTA_ACEITO}' (revogada ou já marcada)"
        )


def _agrupar_convites(
    shares: list[ProjectCollectionShare],
) -> list[ConvitePendente]:
    if not shares:
        return []
    colecoes = {
        colecao.id: colecao
        for colecao in ProjectCollection.query.options(
            joinedload(ProjectCollection.owner)
        ).filter(ProjectCollection.id.in_({share.collection_id for share in shares}))
    }
    por_colecao: dict[int, ConvitePendente] = {}
    for share in shares:
        anterior = por_colecao.get(share.collection_id)
        datas = [share.created_at, anterior.convidado_em if anterior else None]
        por_colecao[share.collection_id] = ConvitePendente(
            colecoes[share.collection_id],
            papel_share_mais_alto(anterior.papel if anterior else None, share.papel),
            max((data for data in datas if data is not None), default=None),
        )
    return sorted(
        por_colecao.values(),
        key=lambda convite: (
            convite.convidado_em or datetime.datetime.min,
            convite.colecao.id,
        ),
        reverse=True,
    )
