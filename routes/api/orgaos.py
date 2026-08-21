"""Endpoint JSON da árvore de órgãos VISÍVEL do usuário (seletor da topnav).

Expõe ``GET /api/orgaos/escopo`` no envelope canônico, reusando o escopo
server-side (``get_visible_orgao_tree``) e a montagem aninhada
(``build_nested_orgao_tree``) — a MESMA fonte de verdade usada pelos seletores
de filtro Jinja. Não reimplementa regra de escopo.

Anexa ao ``main_bp`` ÚNICO; NÃO cria blueprint novo.
"""

from __future__ import annotations

from flask import Response, g

from ..blueprint import main_bp
from ..orgao_scope import build_nested_orgao_tree, get_visible_orgao_tree
from .envelope import ok
from .negotiation import api_login_required


@main_bp.route("/api/orgaos/escopo", methods=["GET"])
@api_login_required
def api_orgaos_escopo() -> Response | tuple[Response, int]:
    """Árvore aninhada de órgãos visível ao usuário corrente (envelope).

    Reusa ``get_visible_orgao_tree`` (escopo: admin vê tudo ativo; não-admin vê
    órgão + descendentes de cada vínculo, sem ancestrais — cada vínculo vira
    raiz) e ``build_nested_orgao_tree`` para aninhar cada nó em ``children``.
    Cada nó traz ``tipo`` e a flag ``is_user_orgao`` que a topnav usa para
    destacar o órgão do usuário no seletor.

    Returns:
        ``ok({tree: [...]})`` (200) com a árvore aninhada (vazia se sem vínculo);
        401 sem sessão.
    """
    flat_nodes = get_visible_orgao_tree(g.user)
    tree = build_nested_orgao_tree(flat_nodes)
    return ok({"tree": tree})
