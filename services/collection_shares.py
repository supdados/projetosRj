"""Compartilhamento de coleção (lado do DONO) e fachada do domínio de shares.

Extraído de ``services/project_collections.py``. O dono concede (share novo
nasce CONVITE pendente, ``exige_aceite=True``), faz upsert de papel, revoga e
reenvia; quando um share vale é decidido SÓ por ``services.collection_access``
/ ``services.collection_participation``. O lado do destinatário
(aceitar/recusar/sair/convites), a poda e os destinatários do card moram em
módulos irmãos e são reexportados aqui — um ponto de import para a rota:

- ``services.collection_invites``: ``aceitar_convite``, ``recusar_convite``,
  ``sair_da_colecao``, ``convites_pendentes_de``, ``convite_pendente``.
- ``services.collection_pruning``: ``podar_itens_sem_editor``,
  ``incluidores_sem_editor``, ``prever_poda``, ``itens_que_saem_por_share``,
  ``itens_incluidos_por``.
- ``services.collection_recipients``: ``status_dos_shares``,
  ``buscar_pessoas_para_compartilhar``.

NÃO commita (a rota commita via ``_mutar``), não lê ``request``/``g``. Toda
mutação invalida o rank map do request.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from models import (
    OrgaoUnidade,
    PAPEIS_SHARE,
    PAPEL_SHARE_EDITOR,
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
from services.collection_audit import (
    auditar_item_colecao,
    auditar_reenvio,
    auditar_share,
)
from services.collection_errors import (
    ColecaoInvalida,
    ConviteIndisponivel,
    bloquear_favoritos,
    exigir_dono,
)
from services.collection_invites import (
    ConvitePendente,
    aceitar_convite,
    convite_pendente,
    convites_pendentes_de,
    recusar_convite,
    sair_da_colecao,
)
from services.collection_pruning import (
    MOTIVO_PODA_INCLUIDOR_SEM_PAPEL,
    MOTIVO_PODA_REBAIXADO,
    MOTIVO_PODA_REVOGADO,
    PrevisaoDaPoda,
    incluidores_sem_editor,
    itens_incluidos_por,
    itens_que_saem_por_share,
    podar_itens_sem_editor,
    prever_poda,
)
from services.collection_recipients import (
    ResumoDoOrgao,
    StatusDoShare,
    buscar_pessoas_para_compartilhar,
    status_dos_shares,
)
from services.notifications import (
    collection_share_recipient_ids,
    notify_collection_invite,
)

_Resposta = ProjectCollectionShareResposta

# Fachada: o domínio de shares inteiro importável daqui (rota, testes).
__all__ = [
    "ConvitePendente",
    "MOTIVO_PODA_INCLUIDOR_SEM_PAPEL",
    "MOTIVO_PODA_REBAIXADO",
    "MOTIVO_PODA_REVOGADO",
    "PrevisaoDaPoda",
    "ResumoDoOrgao",
    "StatusDoShare",
    "aceitar_convite",
    "apagar_shares_da_colecao",
    "aplicar_shares_iniciais",
    "auditar_item_colecao",
    "auditar_item_se_compartilhada",
    "buscar_pessoas_para_compartilhar",
    "collection_ids_com_share",
    "compartilhar_colecao",
    "convite_pendente",
    "convites_pendentes_de",
    "destinatarios_do_share",
    "incluidores_sem_editor",
    "itens_incluidos_por",
    "itens_que_saem_por_share",
    "listar_shares",
    "podar_itens_sem_editor",
    "prever_poda",
    "recusar_convite",
    "reenviar_convite",
    "revogar_share",
    "sair_da_colecao",
    "status_dos_shares",
]


def compartilhar_colecao(
    colecao: ProjectCollection,
    *,
    ator: User,
    user_id: int | None = None,
    orgao_id: int | None = None,
    papel: Any,
    notificar: bool = True,
) -> ProjectCollectionShare:
    """Cria o share como CONVITE pendente (ou faz upsert do papel) — SÓ o dono.

    Exatamente um de ``user_id``/``orgao_id``; Favoritos nunca compartilhável.
    Share novo notifica ``colecao_convite`` (``notificar=False`` deixa o aviso
    ao chamador). Upsert não renotifica nem mexe nas respostas; rebaixar
    editor→viewer poda os itens que a pessoa incluiu. Exemplo:
    ``compartilhar_colecao(colecao, ator=g.user, user_id=7, papel="editor")``.
    """
    exigir_dono(colecao, ator)
    bloquear_favoritos(colecao, "compartilhar")
    _validar_xor_destinatario(user_id, orgao_id)
    _validar_papel_share(papel)
    _validar_destinatario(user_id, orgao_id, ator)
    existente = _share_existente(colecao.id, user_id, orgao_id)
    if existente is not None:
        return _atualizar_papel_share(colecao, existente, papel, ator)
    return _criar_share(colecao, user_id, orgao_id, papel, ator, notificar)


def aplicar_shares_iniciais(
    colecao: ProjectCollection, owner: User, compartilhamentos: list[dict[str, Any]]
) -> None:
    """Shares do POST de criação: viram convites, UM aviso por pessoa alcançada.

    Pessoa + órgão de lotação dela gerariam avisos duplicados com papéis
    contraditórios; vence o papel FINAL mais alto, o mesmo de ``papel_do_usuario``.
    """
    shares: dict[int, ProjectCollectionShare] = {}
    for spec in compartilhamentos:
        share = compartilhar_colecao(
            colecao,
            ator=owner,
            user_id=spec.get("user_id"),
            orgao_id=spec.get("orgao_id"),
            papel=spec.get("papel"),
            notificar=False,
        )
        shares[share.id] = share
    papel_por_pessoa: dict[int, str] = {}
    for share in shares.values():
        for pessoa_id in destinatarios_do_share(colecao, share):
            anterior = papel_por_pessoa.get(pessoa_id)
            papel_por_pessoa[pessoa_id] = papel_share_mais_alto(anterior, share.papel)
    _notificar_convites_agrupados(colecao, owner, papel_por_pessoa)


def revogar_share(colecao: ProjectCollection, share_id: int, *, ator: User) -> bool:
    """Apaga o share, as respostas dele e poda os itens de quem perdeu o editor.

    ``False`` quando o share não existe/não é desta coleção (404 na rota).
    Respostas saem por DELETE explícito: no SQLite sem ``PRAGMA foreign_keys``
    o CASCADE não roda e uma resposta "aceito" órfã seria herdada por um share
    novo que reusasse o rowid (falha ABERTA).
    """
    exigir_dono(colecao, ator)
    share = _share_da_colecao(colecao, share_id)
    if share is None:
        return False
    orfaos = incluidores_sem_editor(colecao)
    auditar_share(colecao, share, "colecao_share_revogado", ator)
    _apagar_respostas([share.id])
    db.session.delete(share)
    podar_itens_sem_editor(
        colecao, ator=ator, motivo=MOTIVO_PODA_REVOGADO, orfaos_antes=orfaos
    )
    invalidate_collection_rank_cache()
    return True


def reenviar_convite(colecao: ProjectCollection, share_id: int, *, ator: User) -> int:
    """Reconvida quem recusou/saiu daquele share (só o dono); devolve quantos.

    Apaga as respostas ``recusado``/``saiu`` do share e notifica de novo quem
    ele ainda alcança. Share legado passa a exigir aceite (quem já tinha acesso
    ganha resposta "aceito" e não perde nada): sem isso, apagar o "saiu" de um
    legado devolveria o acesso sem consentimento. Share alheio → 404; nada a
    reenviar → 422. Exemplo: ``reenviar_convite(colecao, 4, ator=g.user)``.
    """
    exigir_dono(colecao, ator)
    share = _share_da_colecao(colecao, share_id)
    if share is None:
        raise ConviteIndisponivel(
            f"compartilhamento inexistente nesta coleção: share_id={share_id}"
        )
    negativas = _respostas_negativas(share.id)
    if not negativas:
        raise ColecaoInvalida(
            f"ninguém recusou ou saiu do compartilhamento id={share.id}; "
            "nada a reenviar"
        )
    alcancados = destinatarios_do_share(colecao, share)
    if not share.exige_aceite:
        _converter_legado_em_convite(share, alcancados)
    reconvidados = {resposta.user_id for resposta in negativas} & alcancados
    for resposta in negativas:
        db.session.delete(resposta)
    db.session.flush()
    auditar_reenvio(colecao, share, ator, reconvidados)
    notify_collection_invite(colecao, ator.id, share.papel, recipient_ids=reconvidados)
    invalidate_collection_rank_cache()
    return len(reconvidados)


def listar_shares(colecao: ProjectCollection) -> list[ProjectCollectionShare]:
    """Shares da coleção em ordem estável de criação (rota 9, só dono).

    Pessoa e órgão já carregados: o serializer lê os dois, e o lazy-load por
    share tornava o modal linear em N shares.
    """
    return (
        ProjectCollectionShare.query.options(
            joinedload(ProjectCollectionShare.user),
            joinedload(ProjectCollectionShare.orgao),
        )
        .filter_by(collection_id=colecao.id)
        .order_by(ProjectCollectionShare.id)
        .all()
    )


def apagar_shares_da_colecao(colecao_id: int) -> None:
    """DELETE explícito das respostas e dos shares (apagar coleção)."""
    share_ids = [
        share_id
        for (share_id,) in db.session.query(ProjectCollectionShare.id).filter_by(
            collection_id=colecao_id
        )
    ]
    _apagar_respostas(share_ids)
    ProjectCollectionShare.query.filter_by(collection_id=colecao_id).delete()


def destinatarios_do_share(
    colecao: ProjectCollection, share: ProjectCollectionShare
) -> set[int]:
    """Pessoas ATIVAS que o share alcança hoje, sem o dono da coleção."""
    alcancados = collection_share_recipient_ids(
        user_id=share.user_id, orgao_id=share.orgao_id
    )
    return alcancados - {colecao.owner_user_id}


def collection_ids_com_share(collection_ids: Iterable[int]) -> set[int]:
    """Ids (do subconjunto dado) que têm ≥1 share, de qualquer status.

    Flag ``compartilhada`` do card e gatilho da auditoria de itens, em 1 query.
    """
    ids = [int(collection_id) for collection_id in collection_ids]
    if not ids:
        return set()
    rows = (
        db.session.query(ProjectCollectionShare.collection_id)
        .filter(ProjectCollectionShare.collection_id.in_(ids))
        .distinct()
        .all()
    )
    return {collection_id for (collection_id,) in rows}


def auditar_item_se_compartilhada(
    colecao: ProjectCollection, project_id: int, evento: str, ator: User
) -> None:
    """Coleção sem share é gaveta pessoal: mexer nela não vira trilha."""
    if not collection_ids_com_share([colecao.id]):
        return
    auditar_item_colecao(colecao, project_id, evento, ator)


def _criar_share(
    colecao: ProjectCollection,
    user_id: int | None,
    orgao_id: int | None,
    papel: str,
    ator: User,
    notificar: bool,
) -> ProjectCollectionShare:
    share = ProjectCollectionShare(
        collection_id=colecao.id,
        user_id=user_id,
        orgao_id=orgao_id,
        papel=papel,
        created_by_user_id=ator.id,
        exige_aceite=True,
    )
    try:
        with db.session.begin_nested():
            db.session.add(share)
    except IntegrityError:
        # Corrida entre dois upserts: quem perdeu o INSERT relê o vencedor e
        # só ajusta o papel, em vez de estourar 500.
        existente = _share_existente(colecao.id, user_id, orgao_id)
        if existente is None:
            raise
        return _atualizar_papel_share(colecao, existente, papel, ator)
    # Reuso de rowid: resposta órfã de um share apagado não pode ser herdada.
    _apagar_respostas([share.id])
    auditar_share(colecao, share, "colecao_share_concedido", ator)
    if notificar:
        notify_collection_invite(
            colecao,
            ator.id,
            papel,
            recipient_ids=destinatarios_do_share(colecao, share),
        )
    invalidate_collection_rank_cache()
    return share


def _atualizar_papel_share(
    colecao: ProjectCollection,
    share: ProjectCollectionShare,
    papel: str,
    ator: User,
) -> ProjectCollectionShare:
    if share.papel == papel:
        return share
    rebaixa = share.papel == PAPEL_SHARE_EDITOR
    # Órfãos lidos ANTES da troca: só quem perde o editor AGORA leva o motivo.
    orfaos = incluidores_sem_editor(colecao) if rebaixa else set()
    share.papel = papel
    auditar_share(colecao, share, "colecao_share_alterado", ator)
    invalidate_collection_rank_cache()
    if rebaixa:
        podar_itens_sem_editor(
            colecao, ator=ator, motivo=MOTIVO_PODA_REBAIXADO, orfaos_antes=orfaos
        )
    return share


def _share_existente(
    collection_id: int, user_id: int | None, orgao_id: int | None
) -> ProjectCollectionShare | None:
    if user_id is not None:
        return ProjectCollectionShare.query.filter_by(
            collection_id=collection_id, user_id=user_id
        ).first()
    return ProjectCollectionShare.query.filter_by(
        collection_id=collection_id, orgao_id=orgao_id
    ).first()


def _share_da_colecao(
    colecao: ProjectCollection, share_id: int
) -> ProjectCollectionShare | None:
    return ProjectCollectionShare.query.filter_by(
        id=share_id, collection_id=colecao.id
    ).first()


def _apagar_respostas(share_ids: list[int]) -> None:
    if not share_ids:
        return
    _Resposta.query.filter(_Resposta.share_id.in_(share_ids)).delete(
        synchronize_session=False
    )


def _respostas_negativas(share_id: int) -> list[ProjectCollectionShareResposta]:
    negativos = (STATUS_RESPOSTA_RECUSADO, STATUS_RESPOSTA_SAIU)
    return _Resposta.query.filter(
        _Resposta.share_id == share_id, _Resposta.status.in_(negativos)
    ).all()


def _converter_legado_em_convite(
    share: ProjectCollectionShare, alcancados: set[int]
) -> None:
    respondidos = {
        user_id
        for (user_id,) in db.session.query(_Resposta.user_id).filter_by(
            share_id=share.id
        )
    }
    for user_id in sorted(alcancados - respondidos):
        db.session.add(
            _Resposta(share_id=share.id, user_id=user_id, status=STATUS_RESPOSTA_ACEITO)
        )
    share.exige_aceite = True


def _notificar_convites_agrupados(
    colecao: ProjectCollection, ator: User, papel_por_pessoa: dict[int, str]
) -> None:
    ids_por_papel: dict[str, set[int]] = {}
    for pessoa_id, papel in papel_por_pessoa.items():
        ids_por_papel.setdefault(papel, set()).add(pessoa_id)
    for papel, pessoas in ids_por_papel.items():
        notify_collection_invite(colecao, ator.id, papel, recipient_ids=pessoas)


def _validar_xor_destinatario(user_id: int | None, orgao_id: int | None) -> None:
    if (user_id is None) != (orgao_id is None):
        return
    raise ColecaoInvalida(
        f"informe exatamente um de user_id/orgao_id; "
        f"recebido user_id={user_id!r}, orgao_id={orgao_id!r}"
    )


def _validar_papel_share(papel: Any) -> None:
    if papel in PAPEIS_SHARE:
        return
    esperados = "|".join(PAPEIS_SHARE)
    raise ColecaoInvalida(f"papel inválido: {papel!r}; esperado um de {esperados}")


def _validar_destinatario(
    user_id: int | None, orgao_id: int | None, ator: User
) -> None:
    if user_id is not None:
        _validar_destinatario_user(user_id, ator)
        return
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None or not orgao.ativo:
        raise ColecaoInvalida(f"órgão inexistente ou inativo: orgao_id={orgao_id}")


def _validar_destinatario_user(user_id: int, ator: User) -> None:
    if user_id == ator.id:
        raise ColecaoInvalida(
            f"não é possível compartilhar a coleção consigo mesmo (user_id={user_id})"
        )
    destinatario = db.session.get(User, user_id)
    if destinatario is None or destinatario.deleted_at is not None:
        raise ColecaoInvalida(f"usuário inexistente ou inativo: user_id={user_id}")
