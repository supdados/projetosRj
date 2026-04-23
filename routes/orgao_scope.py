"""Escopo de acesso por OrgaoUnidade.

Helpers que traduzem o vinculo de um usuario com orgaos (tabela user_orgao)
em conjuntos de IDs que incluem os descendentes - heranca descendente:
um usuario vinculado a SETD enxerga tudo de SUPDADOS, SUBEDD, etc.

Reusa `get_orgao_descendants` de routes.orgao_tree.
"""

from __future__ import annotations

from urllib.parse import urlencode

from flask import g, redirect, request, url_for

from models import OrgaoUnidade, db
from routes.orgao_tree import get_orgao_descendants


def get_user_orgao_subtree_ids(user) -> set[int]:
    """Retorna o conjunto de orgao_ids acessiveis ao usuario.

    - admin: todos os orgaos ativos.
    - demais: uniao dos subtrees de cada orgao vinculado (inclusivo do no raiz).
    - sem vinculos: conjunto vazio.
    """
    if user is None:
        return set()

    if getattr(user, 'is_admin', False):
        rows = db.session.query(OrgaoUnidade.id).filter(OrgaoUnidade.ativo.is_(True)).all()
        return {row_id for (row_id,) in rows}

    vinculos = getattr(user, 'orgaos', None) or []
    subtree: set[int] = set()
    for uo in vinculos:
        root_id = uo.orgao_id
        subtree.add(root_id)
        subtree.update(get_orgao_descendants(root_id))
    return subtree


def sanitize_orgao_filter_for_user(user, selected_orgao_id):
    """Valida o filtro ?orgao=<id> contra o subtree do usuario.

    Retorna ``(orgao_id|None, invalid: bool)``. Invalido quando o id nao esta
    no subtree de um nao-admin - nesse caso caller redireciona.
    """
    if selected_orgao_id in (None, '', 'None'):
        return None, False
    try:
        orgao_id = int(selected_orgao_id)
    except (TypeError, ValueError):
        return None, True

    if user is None:
        return orgao_id, False
    if getattr(user, 'is_admin', False):
        return orgao_id, False

    subtree = get_user_orgao_subtree_ids(user)
    if orgao_id not in subtree:
        return None, True
    return orgao_id, False


def sanitize_orgao_filter_for_current_user(selected_orgao_id):
    return sanitize_orgao_filter_for_user(getattr(g, 'user', None), selected_orgao_id)


def redirect_to_current_route_without_orgao():
    if request.endpoint:
        target_url = url_for(request.endpoint, **(request.view_args or {}))
    else:
        target_url = request.path

    query_args = request.args.to_dict(flat=False)
    query_args.pop('orgao', None)
    query_string = urlencode(query_args, doseq=True)

    if query_string:
        target_url = f'{target_url}?{query_string}'

    return redirect(target_url)


def expand_orgao_filter_ids(orgao_id) -> set[int]:
    """Expande um orgao_id para o conjunto {proprio + descendentes}.

    Usado quando filtro ?orgao=X deve incluir toda a subtree de X.
    """
    if orgao_id is None:
        return set()
    return {int(orgao_id), *get_orgao_descendants(int(orgao_id))}


def user_can_access_project(user, project) -> bool:
    """Retorna True se o usuario pode acessar o projeto via subtree de orgao.

    Admin sempre acessa. Demais: projeto deve estar no subtree dos orgaos
    vinculados ao usuario (heranca descendente). Projeto sem orgao_id nao e
    acessivel a nao-admins.
    """
    if user is None:
        return False
    if getattr(user, 'is_admin', False):
        return True
    if project is None or project.orgao_id is None:
        return False
    return project.orgao_id in get_user_orgao_subtree_ids(user)
