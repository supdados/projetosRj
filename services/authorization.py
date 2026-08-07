"""Autorização escopada por órgão — ponto único de decisão de acesso.

Concentra a taxonomia de papéis e a resolução de escopo que antes vivia em
``routes/orgao_scope.py``. Vive em ``services/`` (e depende de
``services.orgao_tree``, nunca de ``routes/*``) para que rotas e serviços
possam consumir a mesma decisão sem ciclo de import.

Restrição de cache (TR-3): qualquer memoização de escopo/papel só pode valer
por request (``flask.g``). Nunca TTL cego — revogação de vínculo precisa valer
já no request seguinte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Literal

from flask import g, has_request_context
from sqlalchemy import false, or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import aliased

from models import (
    OrgaoClosure,
    OrgaoUnidade,
    PAPEL_SHARE_EDITOR,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    ProjectMember,
    User,
    db,
)
from services.orgao_tree import get_orgao_descendants
from time_utils import utc_now

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

    from flask import Response

    from models import UserOrgao

PAPEL_LEITOR = "leitor"
PAPEL_EDITOR = "editor"
PAPEL_GESTOR = "gestor"

PAPEL_RANK: dict[str, int] = {
    PAPEL_LEITOR: 10,
    PAPEL_EDITOR: 20,
    PAPEL_GESTOR: 30,
}

# Piso do admin global: vence qualquer papel local, nunca é rebaixado.
ADMIN_RANK: int = 100

ROLE_MAP_CACHE_ATTR = "_authz_role_map"
MEMBERSHIP_MAP_CACHE_ATTR = "_authz_membership_map"
COLLECTION_RANK_CACHE_ATTR = "_authz_collection_rank_map"

FORBIDDEN_PROJECT_MESSAGE = "Você não tem permissão para esta ação neste projeto."

AccessVerdict = Literal["ok", "forbidden", "not_found"]

ACCESS_OK: AccessVerdict = "ok"
ACCESS_FORBIDDEN: AccessVerdict = "forbidden"
ACCESS_NOT_FOUND: AccessVerdict = "not_found"


def get_user_orgao_role_map(user: "User | None") -> dict[int, int]:
    """Retorna ``{orgao_id: rank}`` de tudo que o usuario alcanca.

    - admin: todos os orgaos ativos com ``ADMIN_RANK``.
    - demais: o rank de cada vinculo propagado a subarvore (heranca
      descendente), com sobreposicao pai/filho resolvida por ``max()``.
    - sem vinculos: mapa vazio.

    Exemplo: ``get_user_orgao_role_map(user)[projeto.orgao_id] >= PAPEL_RANK["editor"]``.
    """
    if user is None:
        return {}
    cached = _read_cached_role_map(user)
    if cached is not None:
        return cached
    role_map = _build_role_map(user)
    _write_cached_role_map(user, role_map)
    return role_map


def get_user_orgao_subtree_ids(user: "User | None") -> set[int]:
    """Retorna o conjunto de orgao_ids acessiveis ao usuario.

    - admin: todos os orgaos ativos.
    - demais: uniao dos subtrees de cada orgao vinculado (inclusivo do no raiz).
    - sem vinculos: conjunto vazio.

    Deriva das chaves de ``get_user_orgao_role_map`` — mesma expansao de
    subarvore, ignorando o rank.
    """
    if user is None:
        return set()
    return set(get_user_orgao_role_map(user))


def get_active_membership_map(user: "User | None") -> dict[int, int]:
    """Retorna ``{project_id: rank}`` dos convites ATIVOS do usuario (S4/F3-5).

    UMA query batched, cacheada em ``g`` por request. Ficam de fora: convite
    revogado, expirado (lazy, decidido na leitura — sem cron) e usuario
    soft-deletado. O rank ja sai clampado ao teto de convite (editor).

    Exemplo: ``get_active_membership_map(user).get(projeto.id, 0)``.
    """
    if user is None or getattr(user, "deleted_at", None) is not None:
        return {}
    cached = _read_user_scoped_cache(MEMBERSHIP_MAP_CACHE_ATTR, user)
    if cached is not None:
        return cached
    membership_map = _build_membership_map(user)
    _write_user_scoped_cache(MEMBERSHIP_MAP_CACHE_ATTR, user, membership_map)
    return membership_map


def _build_membership_map(user: "User") -> dict[int, int]:
    teto = PAPEL_RANK[PAPEL_EDITOR]
    return {
        project_id: min(PAPEL_RANK[papel], teto)
        for project_id, papel in _active_membership_rows(getattr(user, "id", None))
        if papel in PAPEL_RANK
    }


def _active_membership_rows(user_id: int | None) -> "Iterable[tuple[int, str]]":
    if not isinstance(user_id, int):
        return []
    try:
        return (
            db.session.query(ProjectMember.project_id, ProjectMember.papel)
            .filter(
                ProjectMember.user_id == user_id,
                ProjectMember.revoked_at.is_(None),
                or_(
                    ProjectMember.expires_at.is_(None),
                    ProjectMember.expires_at > utc_now(),
                ),
            )
            .all()
        )
    except (OperationalError, ProgrammingError):
        # Janela de deploy anterior ao step de migração: sem tabela, sem convite.
        db.session.rollback()
        return []


def get_collection_project_rank_map(user: "User | None") -> dict[int, int]:
    """Retorna ``{project_id: rank}`` derivado de shares de coleção (Fase 2, §5.1).

    Alcança shares diretos no usuário OU no órgão EXATO de lotação (sem
    subárvore — decisão 2026-08-07). Rank: viewer → leitor; editor → editor,
    o MESMO rank intermediário de escrita concedido por convites
    (``papeis_de_convite`` tem teto editor) — nunca gestor. Coleção cujo dono é
    o próprio usuário NUNCA entra (anti auto-escalação: o dono não ganha rank
    compartilhando consigo/seu órgão). Cache por request em ``g`` (TR-3):
    revogar share vale já no request seguinte.
    """
    if user is None or getattr(user, "deleted_at", None) is not None:
        return {}
    cached = _read_user_scoped_cache(COLLECTION_RANK_CACHE_ATTR, user)
    if cached is not None:
        return cached
    rank_map = _build_collection_rank_map(user)
    _write_user_scoped_cache(COLLECTION_RANK_CACHE_ATTR, user, rank_map)
    return rank_map


def _build_collection_rank_map(user: "User") -> dict[int, int]:
    rank_map: dict[int, int] = {}
    for project_id, papel in _collection_share_rows(user):
        rank = _share_papel_rank(papel)
        rank_map[project_id] = max(rank_map.get(project_id, 0), rank)
    return rank_map


def _share_papel_rank(papel: str) -> int:
    # Editor de coleção = rank de escrita dos convites (teto editor); resto lê.
    if papel == PAPEL_SHARE_EDITOR:
        return PAPEL_RANK[PAPEL_EDITOR]
    return PAPEL_RANK[PAPEL_LEITOR]


def _collection_share_rows(user: "User") -> "Iterable[tuple[int, str]]":
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return []
    destinos = [ProjectCollectionShare.user_id == user_id]
    lotacao = lotacao_orgao_ids(user)
    if lotacao:
        destinos.append(ProjectCollectionShare.orgao_id.in_(lotacao))
    try:
        # Savepoint: em Postgres a query falhada invalida a transação; rollback
        # global aqui descartaria mutações pendentes do request.
        with db.session.begin_nested():
            return (
                db.session.query(
                    ProjectCollectionItem.project_id, ProjectCollectionShare.papel
                )
                .join(
                    ProjectCollectionShare,
                    ProjectCollectionShare.collection_id
                    == ProjectCollectionItem.collection_id,
                )
                .join(
                    ProjectCollection,
                    ProjectCollection.id == ProjectCollectionItem.collection_id,
                )
                .join(User, User.id == ProjectCollection.owner_user_id)
                .filter(
                    or_(*destinos),
                    # Dono nunca deriva rank da própria coleção (anti auto-escalação).
                    ProjectCollection.owner_user_id != user_id,
                    User.deleted_at.is_(None),
                )
                .all()
            )
    except (OperationalError, ProgrammingError):
        # Janela de deploy anterior ao step de migração: sem tabela, sem share.
        return []


def lotacao_orgao_ids(user: "User") -> set[int]:
    """Órgãos EXATOS de lotação (linhas de ``user_orgao``), sem subárvore."""
    return {vinculo.orgao_id for vinculo in getattr(user, "orgaos", None) or []}


def invalidate_collection_rank_cache() -> None:
    """Descarta o cache de acesso via coleção após mutação de share/item.

    Mantém o cache por request coerente (TR-3): a próxima leitura no MESMO
    request reflete o share/item recém-mutado.
    """
    if not has_request_context():
        return
    if hasattr(g, COLLECTION_RANK_CACHE_ATTR):
        delattr(g, COLLECTION_RANK_CACHE_ATTR)


def area_project_rank(user: "User | None", project: "Project | None") -> int:
    """Rank do usuario no projeto contando SO vinculo de area (e o piso do admin).

    Convite por projeto (``project_member``, S4) NUNCA entra aqui: reatribuir a
    Area Responsavel por convite e exatamente a escalacao da §5.4 do plano.
    Quando ``effective_project_rank`` passar a somar o convite (S4/F3-6), esta
    funcao continua ignorando-o — e a base da condicao (b) da regra dupla.

    Exemplo: ``area_project_rank(user, projeto) >= PAPEL_RANK["editor"]``.
    """
    if user is None:
        return 0
    if getattr(user, "is_admin", False):
        return ADMIN_RANK
    orgao_id = getattr(project, "orgao_id", None)
    if orgao_id is None:
        return 0
    return get_user_orgao_role_map(user).get(orgao_id, 0)


def effective_project_rank(user: "User | None", project: "Project | None") -> int:
    """Retorna o rank efetivo do usuario no projeto (``0`` = sem acesso).

    ``max(herdado, convite, colecao)`` da §5.2 + Fase 2 §5.1: admin recebe
    ``ADMIN_RANK``; o rank de area propaga pela subarvore; convite e share de
    colecao SOMAM, nunca subtraem, ambos com teto rigido em editor. Projeto sem
    ``orgao_id`` so alcanca rank por admin, convite ou colecao compartilhada.

    Exemplo: ``effective_project_rank(user, projeto) >= PAPEL_RANK["gestor"]``.
    """
    herdado = area_project_rank(user, project)
    if herdado >= ADMIN_RANK:
        return herdado
    return max(
        herdado,
        _invited_project_rank(user, project),
        _collection_project_rank(user, project),
    )


def _collection_project_rank(user: "User | None", project: "Project | None") -> int:
    project_id = getattr(project, "id", None)
    if not isinstance(project_id, int):
        return 0
    derivado = get_collection_project_rank_map(user).get(project_id, 0)
    # Defesa em profundidade: acesso via coleção nunca passa do teto de convite.
    return min(derivado, PAPEL_RANK[PAPEL_EDITOR])


def _invited_project_rank(user: "User | None", project: "Project | None") -> int:
    project_id = getattr(project, "id", None)
    if not isinstance(project_id, int):
        return 0
    direto = get_active_membership_map(user).get(project_id, 0)
    # Defesa em profundidade: o teto editor vale mesmo com linha adulterada.
    return min(direto, PAPEL_RANK[PAPEL_EDITOR])


def user_can_view_project(user: "User | None", project: "Project | None") -> bool:
    """True quando o rank efetivo alcanca ``leitor`` (ver projeto e comentar)."""
    return effective_project_rank(user, project) >= PAPEL_RANK[PAPEL_LEITOR]


def user_can_edit_project(user: "User | None", project: "Project | None") -> bool:
    """True quando o rank efetivo alcanca ``editor`` (criar/editar conteudo)."""
    return effective_project_rank(user, project) >= PAPEL_RANK[PAPEL_EDITOR]


def user_can_manage_project(user: "User | None", project: "Project | None") -> bool:
    """True quando o rank efetivo alcanca ``gestor`` (excluir/concluir)."""
    return effective_project_rank(user, project) >= PAPEL_RANK[PAPEL_GESTOR]


def can_assign_project_to_orgao(user: "User | None", orgao_id: int | None) -> bool:
    """Condicao (a) da §5.4: rank >= editor no orgao DESTINO via vinculo de area.

    Admin sempre pode (inclusive para orgao inativo, caso preservado do fluxo
    atual). Convite (S4) nunca conta: ``project_member`` nao cria vinculo de
    area, entao jamais habilita atribuir a Area Responsavel.

    Exemplo: ``can_assign_project_to_orgao(g.user, novo_orgao_id)``.
    """
    if user is None or orgao_id is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    rank = get_user_orgao_role_map(user).get(int(orgao_id), 0)
    return rank >= PAPEL_RANK[PAPEL_EDITOR]


def user_can_reassign_project_to_orgao(
    user: "User | None", project: "Project | None", orgao_id: int | None
) -> bool:
    """Regra DUPLA da §5.4 para gravar ``Project.orgao_id`` (criacao e edicao).

    Exige (a) ``can_assign_project_to_orgao`` no orgao DESTINO e (b) rank >=
    editor no PROPRIO projeto via vinculo de area ou admin
    (``area_project_rank``). A condicao (b) fecha a "captura": quem so tem acesso
    pontual ao projeto (convite, S4) nao o move para a propria area, por mais
    alto que seja seu rank no destino.

    Na criacao o projeto ainda nao existe — passe ``project=None`` so quando o
    chamador ja tiver garantido (a); do contrario a condicao (b) reprova.

    Exemplo: ``user_can_reassign_project_to_orgao(g.user, projeto, novo_id)``.
    """
    if not can_assign_project_to_orgao(user, orgao_id):
        return False
    return area_project_rank(user, project) >= PAPEL_RANK[PAPEL_EDITOR]


def assignable_orgao_ids(user: "User | None") -> set[int]:
    """IDs de orgaos onde o usuario pode atribuir a Area Responsavel (>= editor).

    Subconjunto de ``get_user_orgao_role_map``; alimenta o picker de escrita
    (``scoped_orgao_options``). Filtros de LEITURA continuam na arvore visivel
    (``get_user_orgao_options``), que nao olha rank.
    """
    role_map = get_user_orgao_role_map(user)
    minimo = PAPEL_RANK[PAPEL_EDITOR]
    return {orgao_id for orgao_id, rank in role_map.items() if rank >= minimo}


def project_access_verdict(
    user: "User | None",
    project: "Project | None",
    min_papel: str,
) -> AccessVerdict:
    """Decisao UNICA 404-vs-403 do contrato S5 (F4-2) — nao replicar por endpoint.

    - ``ACCESS_NOT_FOUND``: projeto ``None`` OU rank efetivo 0. O chamador
      responde o MESMO corpo 404 do caso "id inexistente" (anti-enumeracao,
      F4-2b) — nunca uma mensagem propria.
    - ``ACCESS_FORBIDDEN``: rank >= leitor mas abaixo de ``min_papel``. O
      usuario ja ve o projeto; responder 403 com a mensagem atual do endpoint.
    - ``ACCESS_OK``: rank alcanca ``min_papel``.

    Admin tem ``ADMIN_RANK`` e por isso nunca recebe ``not_found`` por
    autorizacao — so quando o projeto realmente nao existe (``project is None``).

    Uso em rota ``/api/*`` (envelope canonico):
        >>> verdict = project_access_verdict(g.user, project, PAPEL_EDITOR)
        >>> if verdict == ACCESS_NOT_FOUND:
        ...     return fail_not_found()
        >>> if verdict == ACCESS_FORBIDDEN:
        ...     return fail(FORBIDDEN_PROJECT_MESSAGE, status=403, code="forbidden")

    Uso em rota legada (``jsonify``):
        >>> if verdict == ACCESS_NOT_FOUND:
        ...     return jsonify({"success": False, "message": "Recurso não encontrado."}), 404
        >>> if verdict == ACCESS_FORBIDDEN:
        ...     return jsonify({"success": False, "message": FORBIDDEN_PROJECT_MESSAGE}), 403
    """
    rank = effective_project_rank(user, project)
    if project is None or rank < PAPEL_RANK[PAPEL_LEITOR]:
        return ACCESS_NOT_FOUND
    if rank < _papel_to_rank(min_papel):
        return ACCESS_FORBIDDEN
    return ACCESS_OK


def require_project_rank(
    project: "Project | None",
    min_papel: str,
    *,
    user: "User | None" = None,
    message: str | None = None,
) -> "tuple[Response, int] | None":
    """Gate de rank para o CORPO do endpoint: ``None`` libera, ``fail(...)`` nega.

    Checagem no corpo (o projeto ja esta carregado), nunca em decorator.
    Contrato S5 (F4-2, anti-enumeracao): sem sessao => 401 ``unauthenticated``;
    projeto ``None`` OU rank 0 => 404 via ``fail_not_found()`` (corpo byte a
    byte igual ao de id inexistente); rank >= leitor abaixo de ``min_papel`` =>
    403 ``forbidden``. Decisao delegada a ``project_access_verdict``.

    Args:
        project: Projeto ja carregado; ``None`` => 404 (dispensa null-check
            previo no call site).
        min_papel: ``"leitor"`` | ``"editor"`` | ``"gestor"``.
        user: Usuario a avaliar; por padrao ``g.user``.
        message: Mensagem 403 especifica do endpoint. O 404 NAO e customizavel
            por design (F4-2b).

    Exemplo:
        >>> denied = require_project_rank(project, PAPEL_EDITOR)
        >>> if denied:
        ...     return denied
    """
    # Import local: `routes.api.envelope` executa `routes/api/__init__`, que
    # importa este modulo de volta — no topo o ciclo estoura no boot.
    from routes.api.envelope import fail, fail_not_found

    actual_user = user if user is not None else getattr(g, "user", None)
    if actual_user is None:
        return fail(
            "Sessão expirada. Faça login novamente.",
            status=401,
            code="unauthenticated",
        )
    verdict = project_access_verdict(actual_user, project, min_papel)
    if verdict == ACCESS_NOT_FOUND:
        return fail_not_found()
    if verdict == ACCESS_FORBIDDEN:
        return fail(message or FORBIDDEN_PROJECT_MESSAGE, status=403, code="forbidden")
    return None


def _papel_to_rank(papel: str) -> int:
    rank = PAPEL_RANK.get(papel)
    if rank is None:
        raise ValueError(
            f"papel inválido: {papel!r}; esperado um de {sorted(PAPEL_RANK)}"
        )
    return rank


def user_can_access_project(user: "User | None", project: "Project | None") -> bool:
    """Retorna True se o usuario pode LER o projeto: area OU convite ativo (F3-7).

    Wrapper de ``effective_project_rank >= leitor`` — e por aqui que o
    convidado abre detalhe, eventos, reunioes e anexos sem tocar cada endpoint.
    Sem convites cadastrados a semantica e identica a de sempre: admin sempre
    acessa; demais so com o projeto na subarvore dos orgaos vinculados.
    """
    return effective_project_rank(user, project) >= PAPEL_RANK[PAPEL_LEITOR]


def project_visibility_criterion(
    user: "User | None", *, include_collections: bool = True
) -> "ColumnElement[bool]":
    """Filtro §5.3 das listagens de NAO-admin: subtree de area OR convite ativo
    OR item de colecao compartilhada comigo/meu orgao exato (Fase 2, §5.1).

    Uso: ``query.filter(project_visibility_criterion(g.user))`` em query que ja
    envolve ``Project``. Sem vinculo, convite ou share devolve ``false()``
    (lista vazia), como o antigo ``Project.id == -1``.

    ``include_collections=False`` exige visibilidade PROPRIA (area/convite),
    sem o ramo derivado de share de colecao — usado ao semear colecao custom,
    fechando o re-share transitivo apos revogacao.
    """
    clauses = []
    subtree_ids = get_user_orgao_subtree_ids(user)
    if subtree_ids:
        clauses.append(Project.orgao_id.in_(subtree_ids))
    member_project_ids = set(get_active_membership_map(user))
    if member_project_ids:
        clauses.append(Project.id.in_(member_project_ids))
    # O guard pelo rank map (cacheado) preserva o fallback de tabela ausente;
    # o EXISTS correlacionado evita IN materializado de ate 30x200 ids.
    if include_collections and get_collection_project_rank_map(user):
        clauses.append(_collection_visibility_exists(user))
    if not clauses:
        return false()
    return or_(*clauses)


def apply_project_visibility(
    query: Any, user: "User | None", *, include_collections: bool = True
) -> Any:
    """Aplica o criterion de visibilidade com o bypass de admin centralizado."""
    if getattr(user, "is_admin", False):
        return query
    return query.filter(
        project_visibility_criterion(user, include_collections=include_collections)
    )


def _collection_visibility_exists(user: "User") -> "ColumnElement[bool]":
    """EXISTS correlacionado em ``Project.id``: item de colecao ALHEIA (dono
    vivo) com share que alcanca o usuario/orgao exato. Aliases evitam colisao
    quando a query externa ja envolve ``ProjectCollectionItem``/``User``."""
    item = aliased(ProjectCollectionItem)
    share = aliased(ProjectCollectionShare)
    colecao = aliased(ProjectCollection)
    dono = aliased(User)
    destinos = [share.user_id == user.id]
    lotacao = lotacao_orgao_ids(user)
    if lotacao:
        destinos.append(share.orgao_id.in_(lotacao))
    return (
        db.session.query(item.id)
        .join(share, share.collection_id == item.collection_id)
        .join(colecao, colecao.id == item.collection_id)
        .join(dono, dono.id == colecao.owner_user_id)
        .filter(
            item.project_id == Project.id,
            or_(*destinos),
            colecao.owner_user_id != user.id,
            dono.deleted_at.is_(None),
        )
        .correlate(Project)
        .exists()
    )


def _build_role_map(user: "User") -> dict[int, int]:
    if getattr(user, "is_admin", False):
        return _admin_role_map()
    vinculo_ranks = _vinculo_ranks(user)
    if not vinculo_ranks:
        return {}
    return _expand_ranks_to_subtrees(vinculo_ranks)


def _admin_role_map() -> dict[int, int]:
    rows = db.session.query(OrgaoUnidade.id).filter(OrgaoUnidade.ativo.is_(True)).all()
    return {row_id: ADMIN_RANK for (row_id,) in rows}


def _vinculo_ranks(user: "User") -> dict[int, int]:
    """``{orgao_id do vinculo: rank}``, com vinculo duplicado resolvido por max()."""
    ranks: dict[int, int] = {}
    for vinculo in getattr(user, "orgaos", None) or []:
        orgao_id = vinculo.orgao_id
        ranks[orgao_id] = max(ranks.get(orgao_id, 0), _vinculo_rank(vinculo))
    return ranks


def _vinculo_rank(vinculo: "UserOrgao") -> int:
    # Vínculo sem papel (linha legada anterior ao backfill) vale gestor: é o
    # poder que todo vinculado já tinha antes da coluna existir.
    papel = getattr(vinculo, "papel", None) or PAPEL_GESTOR
    return PAPEL_RANK.get(papel, PAPEL_RANK[PAPEL_GESTOR])


def _expand_ranks_to_subtrees(vinculo_ranks: dict[int, int]) -> dict[int, int]:
    """Propaga o rank de cada vinculo aos descendentes; sobreposicao por max()."""
    descendants_by_root = _descendants_by_root(set(vinculo_ranks))
    role_map: dict[int, int] = {}
    for root_id, rank in vinculo_ranks.items():
        for orgao_id in (root_id, *descendants_by_root.get(root_id, ())):
            role_map[orgao_id] = max(role_map.get(orgao_id, 0), rank)
    return role_map


def _descendants_by_root(root_ids: set[int]) -> dict[int, list[int]]:
    """UMA query de closure para todos os vinculos, nao um loop por vinculo."""
    descendants_by_root: dict[int, list[int]] = {}
    for ancestor_id, descendant_id in _closure_rows(root_ids):
        descendants_by_root.setdefault(ancestor_id, []).append(descendant_id)
    # Raiz sem linha de closure cai no BFS de get_orgao_descendants: a closure
    # só é reconstruída pelo sync SIORG, então órgão criado pela tela de admin
    # (ou por fixture de teste) não tem linha nenhuma.
    for root_id in root_ids - set(descendants_by_root):
        descendants_by_root[root_id] = get_orgao_descendants(root_id)
    return descendants_by_root


def _closure_rows(root_ids: set[int]) -> Iterable[tuple[int, int]]:
    try:
        return (
            db.session.query(OrgaoClosure.ancestor_id, OrgaoClosure.descendant_id)
            .filter(OrgaoClosure.ancestor_id.in_(root_ids), OrgaoClosure.depth > 0)
            .all()
        )
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return []


def _user_cache_key(user: "User") -> int | None:
    """Chave de cache por request; ``None`` desliga o cache (TR-3)."""
    if not has_request_context():
        return None
    user_id = getattr(user, "id", None)
    return user_id if isinstance(user_id, int) else None


def _read_user_scoped_cache(attr: str, user: "User") -> dict[int, int] | None:
    key = _user_cache_key(user)
    if key is None:
        return None
    return getattr(g, attr, {}).get(key)


def _write_user_scoped_cache(attr: str, user: "User", value: dict[int, int]) -> None:
    key = _user_cache_key(user)
    if key is None:
        return
    cache = getattr(g, attr, None)
    if cache is None:
        cache = {}
        setattr(g, attr, cache)
    cache[key] = value


def _read_cached_role_map(user: "User") -> dict[int, int] | None:
    return _read_user_scoped_cache(ROLE_MAP_CACHE_ATTR, user)


def _write_cached_role_map(user: "User", role_map: dict[int, int]) -> None:
    _write_user_scoped_cache(ROLE_MAP_CACHE_ATTR, user, role_map)
