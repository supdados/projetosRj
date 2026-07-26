"""Escopo de acesso por OrgaoUnidade.

Helpers que traduzem o vinculo de um usuario com orgaos (tabela user_orgao)
em conjuntos de IDs que incluem os descendentes - heranca descendente:
um usuario vinculado a SETD enxerga tudo de SUPDADOS, SUBEDD, etc.

Reusa `get_orgao_descendants` de routes.orgao_tree. A decisao de escopo em si
(`get_user_orgao_subtree_ids`, `user_can_access_project`) vive em
`services.authorization`; aqui ficam wrappers finos que preservam os call sites.
"""

from __future__ import annotations

from urllib.parse import urlencode

from flask import g, redirect, request, url_for
from sqlalchemy import or_

from models import OrgaoUnidade
from routes.orgao_tree import get_orgao_ancestors, get_orgao_descendants
from services.authorization import (
    get_user_orgao_subtree_ids as _resolve_user_orgao_subtree_ids,
)
from services.authorization import (
    user_can_access_project as _resolve_user_can_access_project,
)


def get_user_orgao_subtree_ids(user) -> set[int]:
    """Wrapper de compatibilidade — implementacao em ``services.authorization``."""
    return _resolve_user_orgao_subtree_ids(user)


def sanitize_orgao_filter_for_user(user, selected_orgao_id):
    """Valida o filtro ?orgao=<id> contra a ARVORE VISIVEL do usuario.

    Retorna ``(orgao_id|None, invalid: bool)``. Invalido quando o id nao esta
    entre os orgaos VISIVEIS de um nao-admin - nesse caso o caller redireciona
    (Jinja) ou devolve 422 (API).

    O conjunto aceito e a arvore visivel (``get_visible_orgao_tree``: ancestrais
    + orgao do vinculo + descendentes) — a MESMA fonte que popula os seletores
    (``get_user_orgao_options``) e a arvore do topnav, onde TODO no e clicavel.
    Validar so contra a subtree (vinculo + descendentes) rejeitava com 422 a
    selecao de um ANCESTRAL, que e oferecido como opcao — inconsistencia
    corrigida aqui. Aceitar um ancestral e seguro: cada consumidor ja clampa a
    query base a subtree do usuario ANTES de aplicar ``expand_orgao_filter_ids``,
    entao o filtro por ancestral intersecta de volta para a subtree (sem
    vazamento de ramos irmaos).
    """
    if selected_orgao_id in (None, "", "None"):
        return None, False
    try:
        orgao_id = int(selected_orgao_id)
    except (TypeError, ValueError):
        return None, True

    if user is None:
        return orgao_id, False
    if getattr(user, "is_admin", False):
        return orgao_id, False

    visible_ids = {node["id"] for node in get_visible_orgao_tree(user)}
    if orgao_id not in visible_ids:
        return None, True
    return orgao_id, False


def sanitize_orgao_filter_for_current_user(selected_orgao_id):
    return sanitize_orgao_filter_for_user(getattr(g, "user", None), selected_orgao_id)


def redirect_to_current_route_without_orgao():
    if request.endpoint:
        target_url = url_for(request.endpoint, **(request.view_args or {}))
    else:
        target_url = request.path

    query_args = request.args.to_dict(flat=False)
    # `area` é alias legado de `orgao` (ver routes/tasks/queries.py:_read_task_filter_values).
    # Sem remover aqui, um `?area=<inválido>` manda o sanitizer rejeitar → redirect → loop.
    query_args.pop("orgao", None)
    query_args.pop("area", None)
    query_string = urlencode(query_args, doseq=True)

    if query_string:
        target_url = f"{target_url}?{query_string}"

    return redirect(target_url)


def expand_orgao_filter_ids(orgao_id) -> set[int]:
    """Expande um orgao_id para o conjunto {proprio + descendentes}.

    Usado quando filtro ?orgao=X deve incluir toda a subtree de X.
    """
    if orgao_id is None:
        return set()
    return {int(orgao_id), *get_orgao_descendants(int(orgao_id))}


def get_user_orgao_siglas(user) -> list[str]:
    """Siglas dos órgãos vinculados diretamente ao usuário (para regras por sigla).

    Usado por regras de negócio que dependem da sigla do órgão (ex.: elegibilidade
    do projeto especial "Inventário"). Admin não é tratado aqui — chamadores
    costumam liberar admin antes de consultar siglas.
    """
    if user is None:
        return []
    vinculos = getattr(user, "orgaos", None) or []
    return [uo.orgao.sigla for uo in vinculos if uo.orgao and uo.orgao.sigla]


def get_user_primary_orgao(user):
    """Retorna o primeiro vinculo OrgaoUnidade do usuario (ou None)."""
    if user is None:
        return None
    vinculos = getattr(user, "orgaos", None) or []
    if not vinculos:
        return None
    return vinculos[0].orgao


def get_user_orgao_breadcrumb(user) -> list[dict]:
    """Lista [{id, sigla, nome, tipo, is_self}] da raiz ate o orgao do usuario.

    Vazio para admin e usuarios sem vinculo. ``is_self`` marca o no terminal
    (o orgao do usuario); ancestrais ficam ``False``.
    """
    primary = get_user_primary_orgao(user)
    if primary is None:
        return []
    ancestor_ids = list(reversed(get_orgao_ancestors(primary.id)))
    chain_ids = ancestor_ids + [primary.id]
    rows = OrgaoUnidade.query.filter(OrgaoUnidade.id.in_(chain_ids)).all()
    by_id = {row.id: row for row in rows}
    breadcrumb = []
    for orgao_id in chain_ids:
        node = by_id.get(orgao_id)
        if node is None:
            continue
        breadcrumb.append(
            {
                "id": node.id,
                "sigla": node.sigla,
                "nome": node.nome,
                "tipo": node.tipo,
                "is_self": node.id == primary.id,
            }
        )
    return breadcrumb


def build_nested_orgao_tree(flat_nodes: list[dict]) -> list[dict]:
    """Converte lista flat de nos em arvore aninhada (cada no recebe ``children``).

    Raizes sao os nos cujo ``pai_id`` nao esta presente entre os ids da lista
    (cobre admin com raiz RJ e nao-admin onde a "raiz" visivel pode ser interna).
    """
    by_id = {node["id"]: dict(node, children=[]) for node in flat_nodes}
    roots: list[dict] = []
    for node in by_id.values():
        pai_id = node.get("pai_id")
        if pai_id in by_id:
            by_id[pai_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def get_visible_orgao_tree(user) -> list[dict]:
    """Retorna nos visiveis ao usuario para montar a arvore do seletor.

    - admin: todos os orgaos ativos.
    - nao-admin com vinculo: ancestrais do orgao primario + o orgao + descendentes.
    - sem vinculo: lista vazia.

    Cada no: ``{id, sigla, nome, tipo, pai_id, is_user_orgao, is_user_ancestor}``.
    """
    if user is None:
        return []

    if getattr(user, "is_admin", False):
        rows = (
            OrgaoUnidade.query.filter(OrgaoUnidade.ativo.is_(True))
            .order_by(
                OrgaoUnidade.pai_id.is_(None).desc(),
                OrgaoUnidade.ordem,
                OrgaoUnidade.sigla,
            )
            .all()
        )
        return [
            {
                "id": r.id,
                "sigla": r.sigla,
                "nome": r.nome,
                "tipo": r.tipo,
                "pai_id": r.pai_id,
                "is_user_orgao": False,
                "is_user_ancestor": False,
                "is_inactive": False,
            }
            for r in rows
        ]

    primary = get_user_primary_orgao(user)
    if primary is None:
        return []
    ancestor_ids = set(get_orgao_ancestors(primary.id))
    descendant_ids = set(get_orgao_descendants(primary.id))
    visible_ids = ancestor_ids | {primary.id} | descendant_ids
    # Ancestrais entram sempre (contexto para montar a árvore); descendentes
    # só se ativos. Antes o filtro `ativo=True` derrubava pais inativos e
    # gerava nós órfãos no build_nested_orgao_tree. O primary (órgão do user)
    # também sempre entra — mesmo que tenha sido desativado após o vínculo.
    always_visible = ancestor_ids | {primary.id}
    rows = (
        OrgaoUnidade.query.filter(OrgaoUnidade.id.in_(visible_ids))
        .filter(
            or_(
                OrgaoUnidade.ativo.is_(True),
                OrgaoUnidade.id.in_(always_visible),
            )
        )
        .order_by(
            OrgaoUnidade.pai_id.is_(None).desc(), OrgaoUnidade.ordem, OrgaoUnidade.sigla
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "sigla": r.sigla,
            "nome": r.nome,
            "tipo": r.tipo,
            "pai_id": r.pai_id,
            "is_user_orgao": r.id == primary.id,
            "is_user_ancestor": r.id in ancestor_ids,
            "is_inactive": not bool(r.ativo),
        }
        for r in rows
    ]


def get_user_orgao_options(user) -> list[dict]:
    """Retorna a subárvore de órgãos visível ao usuário para popular um seletor.

    Reusa ``get_visible_orgao_tree`` (escopo server-side: admin vê tudo ativo;
    não-admin vê ancestrais + órgão + descendentes do vínculo). NÃO reimplementa
    a lógica de escopo — apenas repassa a árvore visível para que os endpoints
    JSON (``/api/projetos``, ``/api/tarefas``, ``/api/projetos-pendentes``) a
    serializem em opções de ``<select>``.

    Args:
        user: Instância de ``User`` (ou ``None``).

    Returns:
        Lista de nós ``{id, sigla, nome, tipo, pai_id, is_user_orgao,
        is_user_ancestor, is_inactive}``, vazia quando não há vínculos.
    """
    return get_visible_orgao_tree(user)


def scoped_orgao_options(user) -> list[dict]:
    """Órgãos atribuíveis ao projeto pelo usuário, para o picker de Área Responsável.

    Admin enxerga todos os órgãos ativos; demais enxergam apenas a própria subtree
    (vínculo + descendentes), também restrita a ativos. Mesma regra de
    ``get_project_edit_data`` (routes/projects/ajax.py), isolada aqui para reuso no
    payload do Detalhe sem duplicar a query.

    Args:
        user: Instância de ``User`` (ou ``None``).

    Returns:
        Lista de ``{id, sigla, nome, pai_id}`` ordenada por ``sigla``; vazia
        quando um não-admin não tem vínculos. ``pai_id`` alimenta a árvore do
        OrgaoTreeSelect no frontend.
    """
    query = OrgaoUnidade.query.filter(OrgaoUnidade.ativo.is_(True))
    if not getattr(user, "is_admin", False):
        subtree_ids = get_user_orgao_subtree_ids(user)
        if not subtree_ids:
            return []
        query = query.filter(OrgaoUnidade.id.in_(subtree_ids))
    rows = query.order_by(OrgaoUnidade.sigla).all()
    return [
        {"id": o.id, "sigla": o.sigla, "nome": o.nome, "pai_id": o.pai_id} for o in rows
    ]


def user_can_access_project(user, project) -> bool:
    """Wrapper de compatibilidade — implementacao em ``services.authorization``."""
    return _resolve_user_can_access_project(user, project)
