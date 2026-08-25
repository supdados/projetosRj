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
from sqlalchemy import func, or_
from sqlalchemy.exc import OperationalError, ProgrammingError

from models import OrgaoClosure, OrgaoUnidade, db
from routes.orgao_tree import get_orgao_ancestors, get_orgao_descendants
from services.authorization import assignable_orgao_ids
from services.authorization import (
    get_user_orgao_subtree_ids as _resolve_user_orgao_subtree_ids,
)
from services.authorization import (
    user_can_access_project as _resolve_user_can_access_project,
)

# Órgão fora da closure ordena por último, nunca vira primary por acidente.
_SEM_CLOSURE = 10**6


def get_user_orgao_subtree_ids(user) -> set[int]:
    """Wrapper de compatibilidade — implementacao em ``services.authorization``."""
    return _resolve_user_orgao_subtree_ids(user)


def sanitize_orgao_filter_for_user(user, selected_orgao_id):
    """Valida o filtro ?orgao=<id> contra o escopo do usuario.

    Retorna ``(orgao_id|None, invalid: bool)``. Invalido quando o id nao esta
    no escopo de um nao-admin - nesse caso o caller redireciona (Jinja) ou
    devolve 422 (API).

    ANCESTRAL de vinculo (que a arvore visivel nao oferece mais) e tratado como
    filtro VAZIO — ``(None, False)`` — em vez de invalido: URL antiga com
    ``?orgao=<ancestral>`` (bookmark, link compartilhado) carrega sem 422/redirect
    e mostra o escopo inteiro, coerente com o gatilho "Todas as areas" que o
    seletor exibe quando o id nao esta entre as opcoes.
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
    if orgao_id in visible_ids:
        return orgao_id, False
    if orgao_id in ancestrais_dos_vinculos(_vinculo_orgao_ids(user)):
        return None, False
    return None, True


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


def expand_orgao_filter_ids(orgao_id, *, incluir_descendentes: bool = True) -> set[int]:
    """Expande um orgao_id para o conjunto {proprio + descendentes}.

    Usado quando filtro ?orgao=X deve incluir toda a subtree de X. Com
    ``incluir_descendentes=False`` (modo ``?apenas_orgao=1`` da SPA) devolve
    apenas ``{orgao_id}``.
    """
    if orgao_id is None:
        return set()
    if not incluir_descendentes:
        return {int(orgao_id)}
    return {int(orgao_id), *get_orgao_descendants(int(orgao_id))}


def parse_apenas_orgao_flag(valor) -> bool:
    """Interpreta o param ``apenas_orgao`` (query string ou corpo JSON)."""
    return str(valor).strip().lower() in ("1", "true", "on")


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


def _orgaos_vinculados(user) -> dict[int, OrgaoUnidade]:
    """``{orgao_id: OrgaoUnidade}`` dos vinculos diretos do usuario, sem repeticao."""
    if user is None:
        return {}
    vinculos = getattr(user, "orgaos", None) or []
    return {uo.orgao.id: uo.orgao for uo in vinculos if uo.orgao is not None}


def _vinculo_orgao_ids(user) -> set[int]:
    """IDs dos vinculos diretos — a MESMA fonte de ``_build_role_map``.

    Le ``vinculo.orgao_id`` em vez de ``vinculo.orgao.id``: nao dispara um SELECT
    por vinculo (N+1) e nao depende do relacionamento estar carregado.
    """
    if user is None:
        return set()
    return {v.orgao_id for v in (getattr(user, "orgaos", None) or [])}


def _profundidade_na_arvore(orgao_ids: set[int]) -> dict[int, int]:
    """``{orgao_id: distancia ate a raiz}`` pela ``orgao_closure``; ausente = stale."""
    try:
        linhas = (
            db.session.query(OrgaoClosure.descendant_id, func.max(OrgaoClosure.depth))
            .filter(OrgaoClosure.descendant_id.in_(orgao_ids))
            .group_by(OrgaoClosure.descendant_id)
            .all()
        )
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return {}
    return {descendant_id: depth for descendant_id, depth in linhas}


def _relacionados_por_closure(
    orgao_ids: set[int], *, chave, alvo, fallback
) -> set[int]:
    """Resolve ancestrais/descendentes de VARIOS orgaos em UMA consulta a closure.

    ``chave``/``alvo`` sao as colunas de ``orgao_closure`` (ancestor/descendant ou
    o inverso). Orgao sem nenhuma linha na closure cai no ``fallback`` unitario —
    a closure so e reconstruida pelo sync SIORG, entao orgao criado pela tela de
    admin (ou por fixture) nao tem linha nenhuma. O proprio orgao volta no
    conjunto (linha de ``depth=0``) e sai na subtracao feita pelos chamadores.
    """
    if not orgao_ids:
        return set()
    linhas = _linhas_de_closure(orgao_ids, chave, alvo)
    relacionados = {alvo_id for _, alvo_id in linhas}
    for orgao_id in orgao_ids - {chave_id for chave_id, _ in linhas}:
        relacionados.update(fallback(orgao_id))
    return relacionados


def _linhas_de_closure(orgao_ids: set[int], chave, alvo) -> list[tuple[int, int]]:
    """Pares da closure, INCLUSIVE ``depth=0``.

    A linha de si mesmo e o que distingue "folha" de "fora da closure": filtrando
    ``depth > 0`` toda folha caia no fallback e cada vinculo virava duas queries.
    Trade-off: orgao criado APOS o ultimo rebuild da closure nao cai no fallback
    (a linha depth=0 do pai existe) e some da arvore — depende do sync SIORG
    rebuildar a closure a cada criacao (services/siorg_sync.py).
    """
    try:
        return db.session.query(chave, alvo).filter(chave.in_(orgao_ids)).all()
    except (OperationalError, ProgrammingError):
        db.session.rollback()
        return []


def ancestrais_dos_vinculos(orgao_ids: set[int]) -> set[int]:
    """Uniao dos ancestrais de todos os orgaos informados (sem os proprios)."""
    return (
        _relacionados_por_closure(
            orgao_ids,
            chave=OrgaoClosure.descendant_id,
            alvo=OrgaoClosure.ancestor_id,
            fallback=get_orgao_ancestors,
        )
        - orgao_ids
    )


def descendentes_dos_vinculos(orgao_ids: set[int]) -> set[int]:
    """Uniao dos descendentes de todos os orgaos informados (sem os proprios)."""
    return (
        _relacionados_por_closure(
            orgao_ids,
            chave=OrgaoClosure.ancestor_id,
            alvo=OrgaoClosure.descendant_id,
            fallback=get_orgao_descendants,
        )
        - orgao_ids
    )


def get_user_primary_orgao(user):
    """Orgao-ancora do usuario: o vinculo mais alto na arvore (ou None sem vinculo).

    ``User.orgaos`` nao tem ``order_by`` — pegar ``vinculos[0]`` devolvia ordens
    diferentes em SQLite (rowid) e MySQL (plano por ``ix_user_orgao_user_id``), e
    um primary errado some com um ramo inteiro do topnav e faz
    ``sanitize_orgao_filter_for_user`` rejeitar um ``?orgao=`` valido com 422.
    Criterio: menor profundidade na ``orgao_closure``, desempate por menor id;
    closure sem resposta cai no menor id. Ex.: vinculos {SETD, SUPDADOS} -> SETD.
    """
    candidatos = _orgaos_vinculados(user)
    if len(candidatos) <= 1:
        return next(iter(candidatos.values()), None)
    profundidades = _profundidade_na_arvore(set(candidatos))
    return min(
        candidatos.values(),
        key=lambda orgao: (profundidades.get(orgao.id, _SEM_CLOSURE), orgao.id),
    )


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
    - nao-admin: uniao, sobre TODOS os vinculos, de (orgao + descendentes).
      ANCESTRAIS ficam de fora: aparecer clicavel um orgao acima do escopo
      (ex.: SETD para quem so acessa SUPDADOS) induzia ao erro — o usuario
      clicava esperando ver mais e via so o proprio escopo. Sem os ancestrais,
      ``build_nested_orgao_tree`` promove cada vinculo a raiz (o ``pai_id``
      nao esta na lista); vinculos em ramos distintos viram multiplas raizes.
    - sem vinculo: lista vazia.

    Cada no: ``{id, sigla, nome, tipo, pai_id, is_user_orgao, is_inactive}``.
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
                "is_inactive": False,
            }
            for r in rows
        ]

    vinculo_ids = _vinculo_orgao_ids(user)
    if not vinculo_ids:
        return []
    visible_ids = vinculo_ids | descendentes_dos_vinculos(vinculo_ids)
    # Descendentes só se ativos; os órgãos dos vínculos entram sempre — mesmo
    # que desativados após o vínculo (é o escopo real do usuário e a raiz do
    # ramo dele na árvore).
    rows = (
        OrgaoUnidade.query.filter(OrgaoUnidade.id.in_(visible_ids))
        .filter(
            or_(
                OrgaoUnidade.ativo.is_(True),
                OrgaoUnidade.id.in_(vinculo_ids),
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
            "is_user_orgao": r.id in vinculo_ids,
            "is_inactive": not bool(r.ativo),
        }
        for r in rows
    ]


def get_user_orgao_options(user) -> list[dict]:
    """Retorna a subárvore de órgãos visível ao usuário para popular um seletor.

    Reusa ``get_visible_orgao_tree`` (escopo server-side: admin vê tudo ativo;
    não-admin vê órgão + descendentes de todos os vínculos, SEM ancestrais). NÃO
    reimplementa a lógica de escopo — apenas repassa a árvore visível para que
    os endpoints JSON (``/api/projetos``, ``/api/tarefas``,
    ``/api/projetos-pendentes``) a serializem em opções de ``<select>``.

    Args:
        user: Instância de ``User`` (ou ``None``).

    Returns:
        Lista de nós ``{id, sigla, nome, tipo, pai_id, is_user_orgao,
        is_inactive}``, vazia quando não há vínculos.
    """
    return get_visible_orgao_tree(user)


def scoped_orgao_options(user) -> list[dict]:
    """Órgãos atribuíveis ao projeto pelo usuário, para o picker de Área Responsável.

    Contexto de ESCRITA (§5.4 do plano): lista apenas os órgãos onde o rank é
    ≥ editor (``assignable_orgao_ids``), sempre restrita a ativos — não basta
    enxergar o órgão para poder atribuir o projeto a ele. Admin segue com todos
    os ativos; com todo vínculo em ``gestor`` o resultado é idêntico ao anterior.
    Seletores de LEITURA/filtro continuam em ``get_user_orgao_options``.

    Args:
        user: Instância de ``User`` (ou ``None``).

    Returns:
        Lista de ``{id, sigla, nome, pai_id}`` ordenada por ``sigla``; vazia
        quando o usuário não tem rank ≥ editor em órgão nenhum. ``pai_id``
        alimenta a árvore do OrgaoTreeSelect no frontend.
    """
    assignable_ids = assignable_orgao_ids(user)
    if not assignable_ids:
        return []
    rows = (
        OrgaoUnidade.query.filter(OrgaoUnidade.ativo.is_(True))
        .filter(OrgaoUnidade.id.in_(assignable_ids))
        .order_by(OrgaoUnidade.sigla)
        .all()
    )
    return [
        {"id": o.id, "sigla": o.sigla, "nome": o.nome, "pai_id": o.pai_id} for o in rows
    ]


def user_can_access_project(user, project) -> bool:
    """Wrapper de compatibilidade — implementacao em ``services.authorization``."""
    return _resolve_user_can_access_project(user, project)
