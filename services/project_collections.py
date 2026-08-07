"""Regras de domínio das coleções de projetos (Fases 1 e 2 do MVP).

Domínio de ``ProjectCollection``/``ProjectCollectionItem``/
``ProjectCollectionShare``: criação atômica, edição/remoção (com bloqueio de
Favoritos), itens idempotentes, compartilhamento com pessoa/órgão
exato (papéis viewer|editor, auditoria em ``AutorizacaoAudit``) e os rollups
agregados em NÚMERO FIXO de queries. Nada de ``request``/``g`` aqui — o
HTTP (gates, envelope, anti-enumeração) fica em ``routes/api/collections.py``.

O service NÃO commita: valida, muta a sessão (com ``flush`` quando precisa de
id) e deixa o commit/rollback para a rota — padrão ``services/project_invites``.

Visibilidade: todo project_id que entra numa coleção é validado contra
``project_visibility_criterion`` do ATOR (admin enxerga tudo); id invisível é
indistinguível de inexistente (``ProjetoForaDoEscopo`` → 404 anti-enumeração).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable

from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import IntegrityError

from catalogs.collection_identity import (
    COLLECTION_COLORS,
    COLLECTION_ICONS,
    FAVORITOS_COLOR,
    FAVORITOS_ICON,
)
from models import (
    ALVO_COLECAO,
    Etapa,
    OrgaoUnidade,
    PAPEIS_SHARE,
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    Task,
    TIPO_COLECAO_CUSTOM,
    TIPO_COLECAO_FAVORITOS,
    User,
    db,
    registrar_autorizacao,
)
from services.authorization import (
    apply_project_visibility,
    invalidate_collection_rank_cache,
    lotacao_orgao_ids,
    project_visibility_criterion,
)
from services.notifications import (
    collection_share_recipient_ids,
    notify_collection_shared,
)
from time_utils import utc_now

MAX_COLECOES_CUSTOM = 20
NOME_MAX_COLECAO = 100
DESCRICAO_MAX_COLECAO = 200
FAVORITOS_NOME = "Favoritos"
PAPEL_COLECAO_DONO = "dono"

BARRA_CONCLUIDA = "concluida"
BARRA_EXECUCAO = "execucao"
BARRA_VENCIDA = "vencida"
BARRA_PREVISTA = "prevista"

_NAO_INFORMADO: Any = object()


class ColecaoInvalida(ValueError):
    """Payload de coleção recusado (nome, ícone/cor, limite, Favoritos)."""


class ProjetoForaDoEscopo(ColecaoInvalida):
    """Projeto inexistente OU invisível ao ator — a rota mapeia para 404."""


class ColecaoSemPermissao(ColecaoInvalida):
    """Ator VÊ a coleção mas o papel não cobre a ação — a rota mapeia para 403."""


def colecao_do_usuario(user_id: int, collection_id: int) -> ProjectCollection | None:
    """Coleção pelo id, SOMENTE se pertence ao usuário (``None`` → 404 na rota)."""
    return ProjectCollection.query.filter_by(
        id=collection_id, owner_user_id=user_id
    ).first()


def listar_colecoes(user_id: int) -> list[tuple[ProjectCollection, str]]:
    """Pares ``(coleção, papel)``: minhas (Favoritos primeiro, custom por
    ``updated_at``) e depois as compartilhadas comigo/meu órgão exato."""
    favoritos = get_or_create_favoritos(user_id)
    custom = (
        ProjectCollection.query.filter_by(
            owner_user_id=user_id, tipo=TIPO_COLECAO_CUSTOM
        )
        .order_by(ProjectCollection.updated_at.desc(), ProjectCollection.id.desc())
        .all()
    )
    minhas = [(colecao, PAPEL_COLECAO_DONO) for colecao in (favoritos, *custom)]
    return [*minhas, *_colecoes_compartilhadas_com(user_id)]


def _colecoes_compartilhadas_com(user_id: int) -> list[tuple[ProjectCollection, str]]:
    """Coleções de terceiros com share para mim/meu órgão; papel mais alto vence."""
    user = db.session.get(User, user_id)
    if user is None:
        return []
    rows = (
        db.session.query(ProjectCollection, ProjectCollectionShare.papel)
        .join(
            ProjectCollectionShare,
            ProjectCollectionShare.collection_id == ProjectCollection.id,
        )
        .join(User, User.id == ProjectCollection.owner_user_id)
        .filter(
            _share_alcanca_usuario(user),
            ProjectCollection.owner_user_id != user_id,
            # Share de dono soft-deletado deixa de conceder acesso.
            User.deleted_at.is_(None),
        )
        .order_by(ProjectCollection.updated_at.desc(), ProjectCollection.id.desc())
        .all()
    )
    por_id: dict[int, tuple[ProjectCollection, str]] = {}
    for colecao, papel in rows:
        registrado = por_id.get(colecao.id)
        if registrado is not None:
            papel = _papel_share_mais_alto(registrado[1], papel)
        por_id[colecao.id] = (colecao, papel)
    return list(por_id.values())


def favoritos_existente(user_id: int) -> ProjectCollection | None:
    """Favoritos já persistida do usuário, sem criar (para leituras puras)."""
    return ProjectCollection.query.filter_by(
        owner_user_id=user_id, tipo=TIPO_COLECAO_FAVORITOS
    ).first()


def get_or_create_favoritos(user_id: int) -> ProjectCollection:
    """Coleção de sistema "Favoritos" do usuário, criada sob demanda.

    Unicidade (1 por usuário) garantida aqui — índice único parcial não é
    portável. Exemplo: ``get_or_create_favoritos(g.user.id)``.
    """
    existente = favoritos_existente(user_id)
    if existente is not None:
        return existente
    favoritos = ProjectCollection(
        owner_user_id=user_id,
        nome=FAVORITOS_NOME,
        tipo=TIPO_COLECAO_FAVORITOS,
        icone=FAVORITOS_ICON,
        cor=FAVORITOS_COLOR,
    )
    db.session.add(favoritos)
    try:
        db.session.flush()
    except IntegrityError:
        # Corrida com request concorrente: quem perdeu o INSERT relê o vencedor.
        db.session.rollback()
        existente = favoritos_existente(user_id)
        if existente is None:
            raise
        return existente
    return favoritos


def criar_colecao(
    owner: User,
    nome: str,
    descricao: str | None,
    icone: str,
    cor: str,
    project_ids: list[int] | None,
    compartilhamentos: list[dict[str, Any]] | None = None,
) -> ProjectCollection:
    """Cria coleção custom + itens + shares iniciais numa única transação.

    ``compartilhamentos`` opcional (default nenhum = "Só eu"): lista de
    ``{"user_id"|"orgao_id": int, "papel": "viewer"|"editor"}``. Exemplo:
    ``criar_colecao(g.user, "Saúde digital", None, "pessoas", "success",
    [3, 7])`` — o chamador commita.
    """
    nome_limpo = _validar_nome(owner.id, nome)
    _validar_icone(icone)
    _validar_cor(cor)
    _validar_limite_colecoes(owner.id)
    ids_visiveis = _validar_projetos_visiveis(owner, project_ids or [])
    colecao = ProjectCollection(
        owner_user_id=owner.id,
        nome=nome_limpo,
        descricao=_validar_descricao(descricao),
        icone=icone,
        cor=cor,
    )
    db.session.add(colecao)
    db.session.flush()
    # Shares antes dos itens: coleção que NASCE compartilhada audita cada item.
    _aplicar_shares_iniciais(colecao, owner, compartilhamentos or [])
    for ordem, project_id in enumerate(ids_visiveis):
        db.session.add(
            ProjectCollectionItem(
                collection_id=colecao.id, project_id=project_id, ordem=ordem
            )
        )
        if compartilhamentos:
            _auditar_item(colecao, project_id, "colecao_projeto_adicionado", owner)
    return colecao


def _aplicar_shares_iniciais(
    colecao: ProjectCollection, owner: User, compartilhamentos: list[dict[str, Any]]
) -> None:
    """Aplica os shares e notifica UMA vez por pessoa alcançada.

    Shares sobrepostos (pessoa + órgão de lotação dela) geravam avisos
    duplicados no mesmo instante, com papéis contraditórios; aqui vence o
    papel mais alto, o mesmo que ``papel_do_usuario`` resolve.
    """
    papel_por_destinatario: dict[int, str] = {}
    for share_spec in compartilhamentos:
        compartilhar_colecao(
            colecao,
            ator=owner,
            user_id=share_spec.get("user_id"),
            orgao_id=share_spec.get("orgao_id"),
            papel=share_spec.get("papel"),
            notificar=False,
        )
        _acumular_destinatarios(papel_por_destinatario, share_spec)
    _notificar_shares_iniciais(colecao, owner, papel_por_destinatario)


def _acumular_destinatarios(
    acumulado: dict[int, str], share_spec: dict[str, Any]
) -> None:
    papel = share_spec.get("papel")
    for destinatario_id in collection_share_recipient_ids(
        user_id=share_spec.get("user_id"), orgao_id=share_spec.get("orgao_id")
    ):
        registrado = acumulado.get(destinatario_id)
        acumulado[destinatario_id] = (
            papel if registrado is None else _papel_share_mais_alto(registrado, papel)
        )


def _notificar_shares_iniciais(
    colecao: ProjectCollection, ator: User, papel_por_destinatario: dict[int, str]
) -> None:
    ids_por_papel: dict[str, set[int]] = {}
    for destinatario_id, papel in papel_por_destinatario.items():
        ids_por_papel.setdefault(papel, set()).add(destinatario_id)
    for papel, destinatarios in ids_por_papel.items():
        notify_collection_shared(colecao, ator.id, papel, recipient_ids=destinatarios)


def editar_colecao(
    colecao: ProjectCollection,
    *,
    nome: Any = _NAO_INFORMADO,
    descricao: Any = _NAO_INFORMADO,
    icone: Any = _NAO_INFORMADO,
    cor: Any = _NAO_INFORMADO,
) -> ProjectCollection:
    """Edita campos informados; Favoritos é imutável (422 na rota).

    Campos ausentes no payload ficam intactos (sentinela ``_NAO_INFORMADO``).
    """
    _bloquear_favoritos(colecao, "editar")
    if nome is not _NAO_INFORMADO:
        colecao.nome = _validar_nome(colecao.owner_user_id, nome, colecao_id=colecao.id)
    if descricao is not _NAO_INFORMADO:
        colecao.descricao = _validar_descricao(descricao)
    if icone is not _NAO_INFORMADO:
        _validar_icone(icone)
        colecao.icone = icone
    if cor is not _NAO_INFORMADO:
        _validar_cor(cor)
        colecao.cor = cor
    # onupdate não dispara em PUT com valores idênticos; bump explícito mantém
    # a ordenação "atualizadas" honesta.
    _bump_updated_at(colecao)
    return colecao


def apagar_colecao(colecao: ProjectCollection) -> None:
    """Hard-delete da coleção, dos itens e dos shares; projetos ficam intactos."""
    _bloquear_favoritos(colecao, "apagar")
    # DELETE explícito de itens E shares: o ondelete CASCADE do banco não é
    # confiável em SQLite sem PRAGMA foreign_keys, e share órfão seria herdado
    # pela próxima coleção via reuso de rowid.
    ProjectCollectionItem.query.filter_by(collection_id=colecao.id).delete()
    ProjectCollectionShare.query.filter_by(collection_id=colecao.id).delete()
    db.session.delete(colecao)
    invalidate_collection_rank_cache()


def adicionar_projeto(
    colecao: ProjectCollection, project_id: int, *, ator: User
) -> bool:
    """Adiciona projeto à coleção; idempotente (``False`` se já estava).

    Ator precisa ser dono ou editor E ver o projeto (anti-escalação). Coleção
    CUSTOM exige visibilidade PRÓPRIA (área/convite): projeto visto só via
    share de outra coleção não pode ser re-semeado — fecharia a revogação.
    Favoritos (nunca compartilhável, nunca concede) aceita a derivada. Bumpa
    ``updated_at`` manualmente (mutação de item não toca a linha da coleção);
    em coleção compartilhada a ação entra na trilha de auditoria.
    """
    _exigir_edicao_de_itens(colecao, ator)
    derivada_ok = colecao.tipo == TIPO_COLECAO_FAVORITOS
    if not projeto_visivel_para(ator, project_id, incluir_derivada=derivada_ok):
        raise ProjetoForaDoEscopo(
            f"projeto inexistente ou fora do escopo: id={project_id}"
        )
    ja_existe = ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, project_id=project_id
    ).first()
    if ja_existe is not None:
        return False
    db.session.add(
        ProjectCollectionItem(
            collection_id=colecao.id,
            project_id=project_id,
            ordem=_proxima_ordem(colecao.id),
        )
    )
    _bump_updated_at(colecao)
    _auditar_item_se_compartilhada(
        colecao, project_id, "colecao_projeto_adicionado", ator
    )
    invalidate_collection_rank_cache()
    return True


def remover_projeto(colecao: ProjectCollection, project_id: int, *, ator: User) -> bool:
    """Remove o par coleção×projeto; ``False`` se não estava na coleção.

    Editor só remove projeto que VÊ (anti-enumeração); dono remove qualquer um
    (inclusive item órfão que saiu do próprio escopo).
    """
    papel = _exigir_edicao_de_itens(colecao, ator)
    if papel != PAPEL_COLECAO_DONO and not projeto_visivel_para(ator, project_id):
        raise ProjetoForaDoEscopo(
            f"projeto inexistente ou fora do escopo: id={project_id}"
        )
    removidos = ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, project_id=project_id
    ).delete()
    if not removidos:
        return False
    _bump_updated_at(colecao)
    _auditar_item_se_compartilhada(
        colecao, project_id, "colecao_projeto_removido", ator
    )
    invalidate_collection_rank_cache()
    return True


def toggle_favorito(user: User, project_id: int) -> bool:
    """Alterna o projeto na coleção Favoritos; ``True`` = agora é favorito.

    Exemplo: ``favorito = toggle_favorito(g.user, project_id)``.
    """
    if not projeto_visivel_para(user, project_id):
        raise ProjetoForaDoEscopo(
            f"projeto inexistente ou fora do escopo: id={project_id}"
        )
    favoritos = get_or_create_favoritos(user.id)
    if remover_projeto(favoritos, project_id, ator=user):
        return False
    return adicionar_projeto(favoritos, project_id, ator=user)


def compartilhar_colecao(
    colecao: ProjectCollection,
    *,
    ator: User,
    user_id: int | None = None,
    orgao_id: int | None = None,
    papel: Any,
    notificar: bool = True,
) -> ProjectCollectionShare:
    """Cria o share (ou faz upsert do papel no duplicado) — SÓ o dono.

    Exatamente um de ``user_id``/``orgao_id``; Favoritos nunca compartilhável.
    ``notificar=False`` deixa o aviso a cargo do chamador (criação com vários
    shares notifica agregado). Exemplo: ``compartilhar_colecao(colecao,
    ator=g.user, user_id=7, papel="editor")`` — o chamador commita.
    """
    _exigir_dono(colecao, ator)
    _bloquear_favoritos(colecao, "compartilhar")
    _validar_xor_destinatario(user_id, orgao_id)
    _validar_papel_share(papel)
    if user_id is not None:
        _validar_destinatario_user(user_id, ator)
    else:
        _validar_destinatario_orgao(orgao_id)
    existente = _share_existente(colecao.id, user_id, orgao_id)
    if existente is not None:
        return _atualizar_papel_share(colecao, existente, papel, ator)
    return _criar_share(colecao, user_id, orgao_id, papel, ator, notificar)


def revogar_share(colecao: ProjectCollection, share_id: int, *, ator: User) -> bool:
    """Apaga o share (acesso derivado some na hora) — SÓ o dono.

    ``False`` quando o share não existe/não é desta coleção (404 na rota);
    atribuições de tarefa/etapa dos alcançados ficam como histórico.
    """
    _exigir_dono(colecao, ator)
    share = ProjectCollectionShare.query.filter_by(
        id=share_id, collection_id=colecao.id
    ).first()
    if share is None:
        return False
    _auditar_share(colecao, share, "colecao_share_revogado", ator)
    db.session.delete(share)
    invalidate_collection_rank_cache()
    return True


def listar_shares(colecao: ProjectCollection) -> list[ProjectCollectionShare]:
    """Shares da coleção em ordem estável de criação (rota 9, só dono)."""
    return (
        ProjectCollectionShare.query.filter_by(collection_id=colecao.id)
        .order_by(ProjectCollectionShare.id)
        .all()
    )


def papel_do_usuario(colecao: ProjectCollection, user: User) -> str | None:
    """``"dono"`` | ``"editor"`` | ``"viewer"`` | ``None`` (não vê a coleção).

    Share direto e share por órgão de lotação exato acumulam: vence o papel
    MAIS ALTO (editor > viewer).
    """
    if user.id == colecao.owner_user_id:
        return PAPEL_COLECAO_DONO
    # Share de dono soft-deletado não concede nem o acesso à própria coleção.
    dono = db.session.get(User, colecao.owner_user_id)
    if dono is None or dono.deleted_at is not None:
        return None
    papeis = {
        share.papel
        for share in ProjectCollectionShare.query.filter(
            ProjectCollectionShare.collection_id == colecao.id,
            _share_alcanca_usuario(user),
        ).all()
    }
    if PAPEL_SHARE_EDITOR in papeis:
        return PAPEL_SHARE_EDITOR
    if PAPEL_SHARE_VIEWER in papeis:
        return PAPEL_SHARE_VIEWER
    return None


def colecao_visivel_para(
    user: User, collection_id: int
) -> tuple[ProjectCollection, str] | None:
    """Coleção + papel quando o usuário a alcança (dono OU share); senão ``None``.

    ``None`` → 404 anti-enumeração na rota. Exemplo:
    ``resultado = colecao_visivel_para(g.user, collection_id)``.
    """
    colecao = db.session.get(ProjectCollection, collection_id)
    if colecao is None:
        return None
    papel = papel_do_usuario(colecao, user)
    if papel is None:
        return None
    return colecao, papel


def collection_ids_com_share(collection_ids: Iterable[int]) -> set[int]:
    """Ids (do subconjunto dado) que têm ≥1 share — flag ``compartilhada`` em
    1 query, sem N+1 no serializer."""
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


def _share_alcanca_usuario(user: User) -> Any:
    """Cláusula SQL: share direto no usuário OU no órgão EXATO de lotação."""
    destinos = [ProjectCollectionShare.user_id == user.id]
    lotacao = lotacao_orgao_ids(user)
    if lotacao:
        destinos.append(ProjectCollectionShare.orgao_id.in_(lotacao))
    return or_(*destinos)


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


def _criar_share(
    colecao: ProjectCollection,
    user_id: int | None,
    orgao_id: int | None,
    papel: str,
    ator: User,
    notificar: bool = True,
) -> ProjectCollectionShare:
    share = ProjectCollectionShare(
        collection_id=colecao.id,
        user_id=user_id,
        orgao_id=orgao_id,
        papel=papel,
        created_by_user_id=ator.id,
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
    _auditar_share(colecao, share, "colecao_share_concedido", ator)
    if notificar:
        notify_collection_shared(
            colecao, ator.id, papel, user_id=user_id, orgao_id=orgao_id
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
    share.papel = papel
    _auditar_share(colecao, share, "colecao_share_alterado", ator)
    invalidate_collection_rank_cache()
    return share


def _exigir_dono(colecao: ProjectCollection, ator: User) -> None:
    if colecao.owner_user_id == ator.id:
        return
    raise ColecaoSemPermissao(
        f"somente o dono gerencia compartilhamentos da coleção id={colecao.id}"
    )


def _exigir_edicao_de_itens(colecao: ProjectCollection, ator: User) -> str:
    papel = papel_do_usuario(colecao, ator)
    if papel in (PAPEL_COLECAO_DONO, PAPEL_SHARE_EDITOR):
        return papel
    raise ColecaoSemPermissao(
        f"papel {papel!r} não permite alterar projetos da coleção id={colecao.id}"
    )


def _papel_share_mais_alto(papel_a: str, papel_b: str) -> str:
    if PAPEL_SHARE_EDITOR in (papel_a, papel_b):
        return PAPEL_SHARE_EDITOR
    return papel_a


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


def _validar_destinatario_user(user_id: int, ator: User) -> None:
    if user_id == ator.id:
        raise ColecaoInvalida(
            f"não é possível compartilhar a coleção consigo mesmo (user_id={user_id})"
        )
    destinatario = db.session.get(User, user_id)
    if destinatario is None or destinatario.deleted_at is not None:
        raise ColecaoInvalida(f"usuário inexistente ou inativo: user_id={user_id}")


def _validar_destinatario_orgao(orgao_id: int | None) -> None:
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None or not orgao.ativo:
        raise ColecaoInvalida(f"órgão inexistente ou inativo: orgao_id={orgao_id}")


def _auditar_share(
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


def _auditar_item_se_compartilhada(
    colecao: ProjectCollection, project_id: int, evento: str, ator: User
) -> None:
    if not collection_ids_com_share([colecao.id]):
        return
    _auditar_item(colecao, project_id, evento, ator)


def _auditar_item(
    colecao: ProjectCollection, project_id: int, evento: str, ator: User
) -> None:
    registrar_autorizacao(
        evento=evento,
        # Ação em lote sem destinatário único; a trilha registra o ator.
        user_id=ator.id,
        ator_id=ator.id,
        alvo_tipo=ALVO_COLECAO,
        alvo_id=colecao.id,
        detalhe={"project_id": project_id},
    )


def projeto_visivel_para(
    ator: User, project_id: int, *, incluir_derivada: bool = True
) -> bool:
    """True se o projeto existe E está no escopo do ator (admin vê tudo).

    ``incluir_derivada=False`` ignora a visibilidade que vem de share de
    coleção — exigência das mutações de coleção CUSTOM (anti re-share).
    """
    query = apply_project_visibility(
        Project.query.filter(Project.id == project_id),
        ator,
        include_collections=incluir_derivada,
    )
    return db.session.query(query.exists()).scalar()


def collection_rollups(
    collection_ids: Iterable[int], viewer: User
) -> dict[int, dict[str, int]]:
    """Agregados por coleção em 1 query (independe de N coleções).

    Retorna ``{collection_id: {projetos, etapas_total, etapas_concluidas,
    progresso_pct}}`` contando SÓ projetos visíveis ao viewer; coleção sem
    projeto visível sai zerada. Etapa concluída = ``iniciada AND done`` nas
    etapas de workflow (regra de ``Project.etapas_concluidas``).
    """
    ids = [int(collection_id) for collection_id in collection_ids]
    rollups = {collection_id: _rollup_zerado() for collection_id in ids}
    if not ids:
        return rollups
    for collection_id, projetos, total, concluidas in _rollup_rows(ids, viewer):
        rollups[collection_id] = {
            "projetos": int(projetos),
            "etapas_total": int(total),
            "etapas_concluidas": int(concluidas),
            "progresso_pct": _progresso_pct(int(concluidas), int(total)),
        }
    return rollups


def colecao_project_rows(
    colecao: ProjectCollection, viewer: User
) -> list[dict[str, Any]]:
    """Linhas da página interna da coleção em 2 queries fixas.

    Cada linha traz os campos do projeto + agregados prontos para
    ``serialize_project_collection_row``: etapas x/y, tarefas x/y, datas
    derivadas das etapas e ``atrasado`` (Vigente com etapa de workflow não
    concluída vencida — regra da lista de projetos, ortogonal ao status).
    """
    rows = [_project_row_dict(row) for row in _project_rows(colecao.id, viewer)]
    tarefas = _task_counts_by_project([row["id"] for row in rows])
    for row in rows:
        total, concluidas = tarefas.get(row["id"], (0, 0))
        row["tarefas_total"] = total
        row["tarefas_concluidas"] = concluidas
    return rows


def colecao_cronograma_rows(
    colecao: ProjectCollection, viewer: User
) -> list[dict[str, Any]]:
    """Linhas do Gantt da coleção (tela 3c) em 2 queries fixas.

    Um item por projeto VISÍVEL ao viewer, na ordem da coleção, com as etapas de
    workflow datadas e a faixa (``barra``) já classificada. Etapa sem nenhuma
    data não vira barra: entra só no contador ``sem_data`` do projeto. Exemplo:
    ``linhas = colecao_cronograma_rows(colecao, g.user)``.
    """
    projetos = [
        _cronograma_projeto_dict(row)
        for row in _cronograma_project_rows(colecao.id, viewer)
    ]
    por_id = {projeto["id"]: projeto for projeto in projetos}
    # utc_now().date(): mesmo relógio UTC do resto do domínio, não o do processo.
    hoje = utc_now().date()
    for etapa in _cronograma_etapas(list(por_id)):
        _acumular_etapa_no_cronograma(por_id[etapa.project_id], etapa, hoje)
    return projetos


def _cronograma_projeto_dict(row: Any) -> dict[str, Any]:
    project_id, titulo, sigla = row
    return {
        "id": project_id,
        "nome": titulo,
        "orgao_sigla": sigla,
        "sem_data": 0,
        "etapas": [],
    }


def _acumular_etapa_no_cronograma(
    projeto: dict[str, Any], etapa: Etapa, hoje: datetime.date
) -> None:
    if etapa.data_inicio is None and etapa.data_fim is None:
        projeto["sem_data"] += 1
        return
    projeto["etapas"].append(
        {
            "id": etapa.id,
            "nome": etapa.descricao,
            "data_inicio": etapa.data_inicio,
            "data_fim": etapa.data_fim,
            "barra": _classificar_barra(etapa, hoje),
        }
    )


def _classificar_barra(etapa: Etapa, hoje: datetime.date) -> str:
    """Faixa da barra: concluída > vencida > em execução > prevista."""
    if etapa.iniciada and etapa.done:
        return BARRA_CONCLUIDA
    if etapa.data_fim is not None and etapa.data_fim < hoje:
        return BARRA_VENCIDA
    # Fim no futuro (ou ausente) já garantido acima; basta o início ter chegado.
    if etapa.data_inicio is not None and etapa.data_inicio <= hoje:
        return BARRA_EXECUCAO
    return BARRA_PREVISTA


def _cronograma_project_rows(collection_id: int, viewer: User) -> list[Any]:
    query = (
        db.session.query(Project.id, Project.titulo, OrgaoUnidade.sigla)
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(OrgaoUnidade, OrgaoUnidade.id == Project.orgao_id)
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .order_by(ProjectCollectionItem.ordem, Project.id)
    )
    return _com_visibilidade(query, viewer).all()


def _cronograma_etapas(project_ids: list[int]) -> list[Etapa]:
    if not project_ids:
        return []
    return (
        Etapa.query.filter(
            Etapa.project_id.in_(project_ids),
            Etapa.entry_type != "google_meeting",
        )
        .order_by(Etapa.project_id, Etapa.ordem, Etapa.id)
        .all()
    )


def _rollup_rows(ids: list[int], viewer: User) -> list[Any]:
    etapa_workflow = and_(
        Etapa.project_id == Project.id, Etapa.entry_type != "google_meeting"
    )
    query = (
        db.session.query(
            ProjectCollectionItem.collection_id,
            func.count(func.distinct(Project.id)),
            func.count(Etapa.id),
            _sum_case(and_(Etapa.iniciada.is_(True), Etapa.done.is_(True))),
        )
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(Etapa, etapa_workflow)
        .filter(ProjectCollectionItem.collection_id.in_(ids))
        .group_by(ProjectCollectionItem.collection_id)
    )
    return _com_visibilidade(query, viewer).all()


def _project_rows(collection_id: int, viewer: User) -> list[Any]:
    workflow = Etapa.entry_type != "google_meeting"
    hoje = utc_now().date()
    query = (
        db.session.query(
            Project.id,
            Project.titulo,
            Project.status,
            OrgaoUnidade.sigla,
            _sum_case(workflow).label("etapas_total"),
            _sum_case(and_(workflow, Etapa.iniciada.is_(True), Etapa.done.is_(True))),
            _sum_case(and_(workflow, Etapa.done.is_(False), Etapa.data_fim < hoje)),
            # Reunião Google fora do min/max: caso sem else vira NULL, ignorado.
            func.min(case((workflow, Etapa.data_inicio))),
            func.max(case((workflow, Etapa.data_fim))),
        )
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(OrgaoUnidade, OrgaoUnidade.id == Project.orgao_id)
        .outerjoin(Etapa, Etapa.project_id == Project.id)
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .group_by(
            Project.id,
            Project.titulo,
            Project.status,
            OrgaoUnidade.sigla,
            ProjectCollectionItem.ordem,
        )
        .order_by(ProjectCollectionItem.ordem, Project.id)
    )
    return _com_visibilidade(query, viewer).all()


def _project_row_dict(row: Any) -> dict[str, Any]:
    pid, titulo, status, sigla, total, concluidas, vencidas, inicio, fim = row
    return {
        "id": pid,
        "nome": titulo,
        "orgao_sigla": sigla,
        "status": status,
        "etapas_total": int(total),
        "etapas_concluidas": int(concluidas),
        "atrasado": status == "Vigente" and int(vencidas) > 0,
        "data_inicio": inicio,
        "data_fim": fim,
    }


def _task_counts_by_project(project_ids: list[int]) -> dict[int, tuple[int, int]]:
    """``{project_id: (total, finalizadas)}`` no MESMO critério do Detalhe de
    Projeto (``routes/api/project_detail.py``): não arquivadas, com etapa e sem
    linhas-filha legadas."""
    if not project_ids:
        return {}
    rows = (
        db.session.query(
            Task.project_id,
            func.count(Task.id),
            _sum_case(Task.status == "finalizada"),
        )
        .filter(
            Task.project_id.in_(project_ids),
            Task.is_archived.is_(False),
            Task.etapa_id.isnot(None),
            Task.legacy_parent_task_id.is_(None),
        )
        .group_by(Task.project_id)
        .all()
    )
    return {pid: (int(total), int(done)) for pid, total, done in rows}


def _sum_case(condicao: Any) -> Any:
    return func.coalesce(func.sum(case((condicao, 1), else_=0)), 0)


def _com_visibilidade(query: Any, viewer: User) -> Any:
    return apply_project_visibility(query, viewer)


def _rollup_zerado() -> dict[str, int]:
    return {
        "projetos": 0,
        "etapas_total": 0,
        "etapas_concluidas": 0,
        "progresso_pct": 0,
    }


def _progresso_pct(concluidas: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100 * concluidas / total)


def _bump_updated_at(colecao: ProjectCollection) -> None:
    colecao.updated_at = utc_now()


def _bloquear_favoritos(colecao: ProjectCollection, acao: str) -> None:
    if colecao.tipo != TIPO_COLECAO_FAVORITOS:
        return
    raise ColecaoInvalida(
        f"não é possível {acao} a coleção Favoritos (coleção de sistema)"
    )


def _validar_nome(owner_id: int, nome: Any, *, colecao_id: int | None = None) -> str:
    if not isinstance(nome, str) or not nome.strip():
        raise ColecaoInvalida(f"nome inválido: {nome!r}; esperado texto não vazio")
    nome_limpo = nome.strip()
    if len(nome_limpo) > NOME_MAX_COLECAO:
        raise ColecaoInvalida(
            f"nome com {len(nome_limpo)} caracteres; máximo {NOME_MAX_COLECAO}"
        )
    # Reservado: um custom "Favoritos" quebraria o get-or-create da coleção
    # de sistema (uq_project_collection_owner_nome não distingue tipo).
    if nome_limpo.casefold() == FAVORITOS_NOME.casefold():
        raise ColecaoInvalida(f"nome reservado: {nome_limpo!r}")
    _validar_nome_unico(owner_id, nome_limpo, colecao_id)
    return nome_limpo


def _validar_descricao(descricao: Any) -> str | None:
    if descricao is None:
        return None
    if not isinstance(descricao, str):
        raise ColecaoInvalida(f"descrição inválida: {descricao!r}; esperado texto")
    limpa = descricao.strip()
    if len(limpa) > DESCRICAO_MAX_COLECAO:
        raise ColecaoInvalida(
            f"descrição com {len(limpa)} caracteres; máximo {DESCRICAO_MAX_COLECAO}"
        )
    return limpa or None


def _validar_nome_unico(owner_id: int, nome: str, colecao_id: int | None) -> None:
    query = ProjectCollection.query.filter_by(owner_user_id=owner_id, nome=nome)
    if colecao_id is not None:
        query = query.filter(ProjectCollection.id != colecao_id)
    if db.session.query(query.exists()).scalar():
        raise ColecaoInvalida(f"já existe uma coleção com o nome {nome!r}")


def _validar_icone(icone: Any) -> None:
    if icone in COLLECTION_ICONS:
        return
    esperados = "|".join(sorted(COLLECTION_ICONS))
    raise ColecaoInvalida(f"ícone inválido: {icone!r}; esperado um de {esperados}")


def _validar_cor(cor: Any) -> None:
    if cor in COLLECTION_COLORS:
        return
    esperados = "|".join(sorted(COLLECTION_COLORS))
    raise ColecaoInvalida(
        f"cor inválida: {cor!r}; esperado família da régua ({esperados})"
    )


def _validar_limite_colecoes(owner_id: int) -> None:
    total = ProjectCollection.query.filter_by(
        owner_user_id=owner_id, tipo=TIPO_COLECAO_CUSTOM
    ).count()
    if total >= MAX_COLECOES_CUSTOM:
        raise ColecaoInvalida(
            f"limite de {MAX_COLECOES_CUSTOM} coleções atingido ({total} existentes)"
        )


def _validar_projetos_visiveis(owner: User, project_ids: list[int]) -> list[int]:
    ids_unicos = list(dict.fromkeys(int(pid) for pid in project_ids))
    if not ids_unicos:
        return []
    visiveis = _ids_visiveis(owner, ids_unicos)
    invisiveis = [pid for pid in ids_unicos if pid not in visiveis]
    if invisiveis:
        raise ProjetoForaDoEscopo(
            f"projetos inexistentes ou fora do escopo: ids={invisiveis}"
        )
    return ids_unicos


def _ids_visiveis(ator: User, project_ids: list[int]) -> set[int]:
    # Coleção custom nasce só com visibilidade própria (anti re-share).
    query = apply_project_visibility(
        db.session.query(Project.id).filter(Project.id.in_(project_ids)),
        ator,
        include_collections=False,
    )
    return {pid for (pid,) in query.all()}


def _proxima_ordem(collection_id: int) -> int:
    maior = (
        db.session.query(func.max(ProjectCollectionItem.ordem))
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .scalar()
    )
    return 0 if maior is None else maior + 1
