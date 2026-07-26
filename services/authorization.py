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


def effective_project_rank(user: "User | None", project: "Project | None") -> int:
    """Retorna o rank efetivo do usuario no projeto (``0`` = sem acesso).

    Admin recebe ``ADMIN_RANK``; os demais herdam o rank do orgao responsavel
    pelo projeto. O componente direto (convite por projeto) e fixo em ``0``
    nesta fase — entra com ``project_member``.

    Exemplo: ``effective_project_rank(user, projeto) >= PAPEL_RANK["gestor"]``.
    """
    if user is None:
        return 0
    if getattr(user, "is_admin", False):
        return ADMIN_RANK
    orgao_id = getattr(project, "orgao_id", None)
    if orgao_id is None:
        return 0
    return get_user_orgao_role_map(user).get(orgao_id, 0)


def user_can_view_project(user: "User | None", project: "Project | None") -> bool:
    """True quando o rank efetivo alcanca ``leitor`` (ver projeto e comentar)."""
    return effective_project_rank(user, project) >= PAPEL_RANK[PAPEL_LEITOR]


def user_can_edit_project(user: "User | None", project: "Project | None") -> bool:
    """True quando o rank efetivo alcanca ``editor`` (criar/editar conteudo)."""
    return effective_project_rank(user, project) >= PAPEL_RANK[PAPEL_EDITOR]


def user_can_manage_project(user: "User | None", project: "Project | None") -> bool:
    """True quando o rank efetivo alcanca ``gestor`` (excluir/concluir)."""
    return effective_project_rank(user, project) >= PAPEL_RANK[PAPEL_GESTOR]


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
