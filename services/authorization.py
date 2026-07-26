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

from typing import TYPE_CHECKING, Iterable

from flask import g, has_request_context
from sqlalchemy.exc import OperationalError, ProgrammingError

from models import OrgaoClosure, OrgaoUnidade, db
from services.orgao_tree import get_orgao_descendants

if TYPE_CHECKING:
    from flask import Response

    from models import Project, User, UserOrgao

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

FORBIDDEN_PROJECT_MESSAGE = "Você não tem permissão para esta ação neste projeto."


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

    Admin recebe ``ADMIN_RANK``; os demais herdam o rank do orgao responsavel
    pelo projeto. O componente direto (convite por projeto) e fixo em ``0``
    nesta fase — entra com ``project_member``.

    Exemplo: ``effective_project_rank(user, projeto) >= PAPEL_RANK["gestor"]``.
    """
    return area_project_rank(user, project)


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


def require_project_rank(
    project: "Project | None",
    min_papel: str,
    *,
    user: "User | None" = None,
    message: str | None = None,
) -> "tuple[Response, int] | None":
    """Gate de rank para o CORPO do endpoint: ``None`` libera, ``fail(...)`` nega.

    Checagem no corpo (o projeto ja esta carregado), nunca em decorator. Contrato
    HTTP desta fase: sem sessao => 401 ``unauthenticated``; rank insuficiente,
    inclusive rank 0 => 403 ``forbidden``. A unificacao 404 anti-enumeracao e S5
    — nao antecipar aqui.

    Args:
        project: Projeto ja carregado (``None`` reprova qualquer nao-admin).
        min_papel: ``"leitor"`` | ``"editor"`` | ``"gestor"``.
        user: Usuario a avaliar; por padrao ``g.user``.
        message: Mensagem 403 especifica do endpoint (mantem o texto atual).

    Exemplo:
        >>> denied = require_project_rank(project, PAPEL_EDITOR)
        >>> if denied:
        ...     return denied
    """
    # Import local: `routes.api.envelope` executa `routes/api/__init__`, que
    # importa este modulo de volta — no topo o ciclo estoura no boot.
    from routes.api.envelope import fail

    actual_user = user if user is not None else getattr(g, "user", None)
    if actual_user is None:
        return fail(
            "Sessão expirada. Faça login novamente.",
            status=401,
            code="unauthenticated",
        )
    if effective_project_rank(actual_user, project) >= _papel_to_rank(min_papel):
        return None
    return fail(message or FORBIDDEN_PROJECT_MESSAGE, status=403, code="forbidden")


def _papel_to_rank(papel: str) -> int:
    rank = PAPEL_RANK.get(papel)
    if rank is None:
        raise ValueError(
            f"papel inválido: {papel!r}; esperado um de {sorted(PAPEL_RANK)}"
        )
    return rank


def user_can_access_project(user: "User | None", project: "Project | None") -> bool:
    """Retorna True se o usuario pode acessar o projeto via subtree de orgao.

    Admin sempre acessa. Demais: projeto deve estar no subtree dos orgaos
    vinculados ao usuario (heranca descendente). Projeto sem orgao_id nao e
    acessivel a nao-admins.
    """
    if user is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    if project is None or project.orgao_id is None:
        return False
    return project.orgao_id in get_user_orgao_subtree_ids(user)


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


def _role_map_cache_key(user: "User") -> int | None:
    """Chave de cache por request; ``None`` desliga o cache (TR-3)."""
    if not has_request_context():
        return None
    user_id = getattr(user, "id", None)
    return user_id if isinstance(user_id, int) else None


def _read_cached_role_map(user: "User") -> dict[int, int] | None:
    key = _role_map_cache_key(user)
    if key is None:
        return None
    return getattr(g, ROLE_MAP_CACHE_ATTR, {}).get(key)


def _write_cached_role_map(user: "User", role_map: dict[int, int]) -> None:
    key = _role_map_cache_key(user)
    if key is None:
        return
    cache = getattr(g, ROLE_MAP_CACHE_ATTR, None)
    if cache is None:
        cache = {}
        setattr(g, ROLE_MAP_CACHE_ATTR, cache)
    cache[key] = role_map
