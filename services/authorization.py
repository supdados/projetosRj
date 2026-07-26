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

from typing import TYPE_CHECKING

from models import OrgaoUnidade, db
from services.orgao_tree import get_orgao_descendants

if TYPE_CHECKING:
    from models import Project, User

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


def get_user_orgao_subtree_ids(user: "User | None") -> set[int]:
    """Retorna o conjunto de orgao_ids acessiveis ao usuario.

    - admin: todos os orgaos ativos.
    - demais: uniao dos subtrees de cada orgao vinculado (inclusivo do no raiz).
    - sem vinculos: conjunto vazio.
    """
    if user is None:
        return set()

    if getattr(user, "is_admin", False):
        rows = (
            db.session.query(OrgaoUnidade.id).filter(OrgaoUnidade.ativo.is_(True)).all()
        )
        return {row_id for (row_id,) in rows}

    vinculos = getattr(user, "orgaos", None) or []
    subtree: set[int] = set()
    for uo in vinculos:
        root_id = uo.orgao_id
        subtree.add(root_id)
        subtree.update(get_orgao_descendants(root_id))
    return subtree


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
