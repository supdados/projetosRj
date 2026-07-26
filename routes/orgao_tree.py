"""Re-export de compatibilidade: a implementação vive em `services/orgao_tree.py`.

Mantido para não quebrar os call sites existentes (`from routes.orgao_tree import ...`).
Código novo deve importar direto de `services.orgao_tree`.
"""

from services.orgao_tree import (
    backfill_orgao_tipo_ids,
    compute_orgao_depth,
    compute_subtree_height,
    ensure_default_orgao_tipos,
    find_orgao_tipo,
    get_orgao_ancestors,
    get_orgao_descendants,
    get_orgao_tipo_options,
    get_tipo_rank_map,
    is_valid_parent_tipo,
    normalize_orgao_form,
    rebuild_orgao_closure,
    resolve_orgao_tipo,
    validate_orgao_move,
    would_create_cycle,
)

__all__ = [
    "backfill_orgao_tipo_ids",
    "compute_orgao_depth",
    "compute_subtree_height",
    "ensure_default_orgao_tipos",
    "find_orgao_tipo",
    "get_orgao_ancestors",
    "get_orgao_descendants",
    "get_orgao_tipo_options",
    "get_tipo_rank_map",
    "is_valid_parent_tipo",
    "normalize_orgao_form",
    "rebuild_orgao_closure",
    "resolve_orgao_tipo",
    "validate_orgao_move",
    "would_create_cycle",
]
