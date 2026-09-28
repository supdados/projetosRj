import csv
import datetime
import io

from sqlalchemy.orm import joinedload

from flask import (
    flash,
    g,
    make_response,
    redirect,
    request,
    url_for,
)

from models import (
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectHistory,
    TIPO_COLECAO_FAVORITOS,
    db,
)
from catalogs.abep import ABEP_INDICADORES_OPTIONS
from catalogs.delivery_types import DELIVERY_TYPES_OPTIONS
from catalogs.inventario import any_orgao_allows_inventario

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.orgao_scope import (
    get_user_orgao_options,
    get_user_orgao_siglas,
    scoped_orgao_options,
)
from services.atraso import hoje_utc
from services.authorization import project_visibility_criterion
from services.csv_safety import safe_csv_text as _safe_csv_text
from routes.projects.list_filters import (
    ProjectsListFilters,
    apply_projects_list_filters,
)
from routes.shared import (
    get_or_404,
    get_goal_catalog_context,
)


def _favorito_project_ids(project_ids):
    """Ids favoritados pelo usuário corrente, em UMA query e sem efeito colateral.

    Não usa ``get_or_create_favoritos``: uma listagem (GET) não pode criar a
    coleção de sistema — sem Favoritos, o conjunto é vazio.
    """
    if not project_ids:
        return set()
    rows = (
        db.session.query(ProjectCollectionItem.project_id)
        .join(
            ProjectCollection,
            ProjectCollection.id == ProjectCollectionItem.collection_id,
        )
        .filter(
            ProjectCollection.owner_user_id == g.user.id,
            ProjectCollection.tipo == TIPO_COLECAO_FAVORITOS,
            ProjectCollectionItem.project_id.in_(project_ids),
        )
        .all()
    )
    return {project_id for (project_id,) in rows}


def build_projects_list_context(
    *,
    selected_priority=None,
    selected_status=None,
    selected_orgao_id=None,
    apenas_orgao=False,
    selected_atraso=None,
    selected_special_project=None,
    selected_delivery_type=None,
    selected_abep_indicator=None,
    selected_objetivo=None,
    selected_colecao_id=None,
    excluded_colecao_id=None,
    search_query="",
    page=1,
    per_page=40,
):
    """Monta os dados da Lista de Projetos, respeitando o escopo de órgão.

    Centraliza as queries/filtros/paginação de ``GET /api/projetos``. O escopo de
    órgão é server-side (não-admin restrito à subárvore). O chamador é
    responsável por sanitizar o filtro de órgão via
    ``sanitize_orgao_filter_for_current_user`` antes de passar
    ``selected_orgao_id``.

    Args:
        selected_priority: Filtro de prioridade (ou ``None``/"").
        selected_status: Filtro de status; o chamador define o default "Vigente"
            (mantido aqui apenas como filtro, sem reescrever o default).
        selected_orgao_id: ID de órgão já validado para o usuário (ou ``None``).
        apenas_orgao: ``True`` restringe ao órgão selecionado SEM os descendentes.
        selected_atraso: "atrasado" | "no_prazo" | "" (critério único de
            ``services/atraso.py``, aplicado em SQL sobre projetos vigentes).
        selected_special_project: "ABEP" | "TCE" | "Fórum de simplificação" | "" .
        selected_delivery_type: Tipo de entrega (ou "").
        selected_abep_indicator: Indicador ABEP (normalizado internamente).
        selected_objetivo: ID de objetivo como string (ou "").
        selected_colecao_id: ID de coleção do próprio usuário (ou ``None``);
            coleção de outro dono resulta em lista vazia, não em erro.
        excluded_colecao_id: ID de coleção do próprio usuário cujos projetos
            ficam FORA da lista (picker "adicionar projetos"); coleção de outro
            dono não exclui nada.
        search_query: Texto de busca (título/órgão/indicador/ID).
        page: Página solicitada (1-based) da lista paginada.
        per_page: Tamanho da página (default 40; o chamador é responsável por
            limitar valores vindos do cliente).

    Returns:
        ``dict`` com a lista paginada (``projects``), o conjunto
        ``favorito_project_ids`` da página, os filtros aplicados/selecionados, as
        opções de filtro (incluindo ``orgaos_options`` e
        ``ABEP_INDICADORES_OPTIONS``) e os metadados de paginação.
    """
    filters = ProjectsListFilters(
        selected_orgao_id=selected_orgao_id,
        apenas_orgao=apenas_orgao,
        selected_status=selected_status,
        selected_priority=selected_priority,
        selected_atraso=selected_atraso,
        selected_special_project=selected_special_project,
        selected_delivery_type=selected_delivery_type,
        selected_abep_indicator=selected_abep_indicator,
        selected_objetivo=selected_objetivo,
        selected_colecao_id=selected_colecao_id,
        excluded_colecao_id=excluded_colecao_id,
        search_query=search_query,
    )
    query = apply_projects_list_filters(Project.query, filters, g.user)
    selected_abep_indicator = filters.selected_abep_indicator
    selected_objetivo = filters.selected_objetivo

    total_projects = query.count()
    total_pages = (total_projects + per_page - 1) // per_page  # Ceiling division

    # Clampar page fora do intervalo válido (evita offset negativo com page<=0)
    if total_pages == 0:
        page = 1
    else:
        page = max(1, min(page or 1, total_pages))

    projects_paginated = (
        query.options(joinedload(Project.orgao_ref))
        .order_by(Project.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    options_query = Project.query
    if not g.user.is_admin:
        options_query = options_query.filter(project_visibility_criterion(g.user))

    priorities_options = sorted(
        valor
        for (valor,) in options_query.with_entities(Project.prioridade).distinct()
        if valor
    )
    statuses_options = sorted(
        valor
        for (valor,) in options_query.with_entities(Project.status).distinct()
        if valor
    )
    atrasos_options = [("no_prazo", "No prazo"), ("atrasado", "Atrasado")]
    objetivos, _, _ = (
        get_goal_catalog_context()
    )  # Para o modal de adicionar projeto e filtro

    special_projects_options = ["ABEP", "TCE", "Fórum de simplificação"]
    if g.user.is_admin or any_orgao_allows_inventario(get_user_orgao_siglas(g.user)):
        special_projects_options.append("Inventário")
    delivery_types_options = list(DELIVERY_TYPES_OPTIONS)
    has_advanced_filters_active = any(
        [
            selected_atraso,
            selected_special_project,
            selected_delivery_type,
            selected_abep_indicator,
            selected_objetivo,
        ]
    )

    # Verificar se há filtros ativos (para mostrar botão "Limpar")
    has_active_filters = False
    if search_query:
        has_active_filters = True
    if selected_priority:
        has_active_filters = True
    if selected_status and selected_status != "Vigente":  # Vigente é o padrão
        has_active_filters = True
    if has_advanced_filters_active:
        has_active_filters = True
    if selected_orgao_id:
        has_active_filters = True
    if selected_colecao_id:
        has_active_filters = True

    # Subárvore de órgãos visível ao usuário (escopo server-side) para popular o
    # <select> de filtro de órgão na SPA.
    orgaos_options = get_user_orgao_options(g.user)
    # Picker do modal Criar Projeto (§5.4/F2-6): atribuir Área Responsável exige
    # rank >= editor — filtro da lista acima continua por visibilidade.
    orgaos_assignable_options = scoped_orgao_options(g.user)

    return {
        "projects": projects_paginated,
        "favorito_project_ids": _favorito_project_ids(
            [projeto.id for projeto in projects_paginated]
        ),
        "page": page,
        "total_pages": total_pages,
        "total_projects": total_projects,
        "per_page": per_page,
        "search_query": search_query,
        "selected_priority": selected_priority,
        "selected_status": selected_status,
        "selected_atraso": selected_atraso,
        "selected_special_project": selected_special_project,
        "selected_delivery_type": selected_delivery_type,
        "selected_abep_indicator": selected_abep_indicator,
        "selected_objetivo": selected_objetivo,
        "selected_colecao": selected_colecao_id,
        "selected_orgao": selected_orgao_id,
        "priorities": priorities_options,
        "statuses": statuses_options,
        "atrasos_options": atrasos_options,
        "objetivos": objetivos,
        "orgaos_options": orgaos_options,
        "orgaos_assignable_options": orgaos_assignable_options,
        "special_projects_options": special_projects_options,
        "delivery_types_options": delivery_types_options,
        "abep_indicadores_options": ABEP_INDICADORES_OPTIONS,
        "has_active_filters": has_active_filters,
        "has_advanced_filters_active": has_advanced_filters_active,
    }


@main_bp.route("/projects")
@login_required
def list_projects():
    """KEEP-ENDPOINT: redireciona (302) para /projetos (SPA).

    O path /projects é preservado para bookmarks antigos e para os redirects de
    produção (``routes/tasks/views.py::project_tasks``). A UI e os dados vivem na
    SPA (``GET /api/projetos``). A tela Jinja list.html foi cortada na migração.
    """
    query = request.query_string.decode()
    return redirect("/projetos" + ("?" + query if query else ""))


def build_projetos_pendentes_context(
    selected_orgao_id: int | None,
    *,
    apenas_orgao: bool = False,
    filtro_periodo: str = "atrasados",
    selected_responsavel: str = "",
    selected_priority: str = "",
    search_query: str = "",
    pending_page: int = 1,
) -> dict[str, object]:
    """Monta Pendentes com paginação e projeções SQL, usando o relógio canônico."""
    from .views_pending import build_pending_context

    return build_pending_context(
        selected_orgao_id,
        today=hoje_utc(),
        apenas_orgao=apenas_orgao,
        filtro_periodo=filtro_periodo,
        selected_responsavel=selected_responsavel,
        selected_priority=selected_priority,
        search_query=search_query,
        pending_page=pending_page,
    )


@main_bp.route("/project/<int:project_id>")
@login_required
def project_detail(project_id):
    """Resolve o deep-link Jinja e redireciona (302) para o detalhe na SPA.

    KEEP-ENDPOINT: o endpoint ``main.project_detail`` permanece porque o
    ``target_url`` PERSISTIDO em notificações (``services/notifications.py``) e a
    busca apontam para ``/project/<id>``. Uma notificação antiga abre agora a SPA
    em ``/projetos/<id>``; o controle de acesso é reforçado pela API do detalhe
    (``/api/projetos/<id>``). A tela Jinja ``detail.html`` foi cortada.

    Preserva o query string original (ex.: ``?focus_etapa=<id>`` vindo da busca)
    para que o deep-link chegue intacto à SPA.
    """
    query_string = request.query_string.decode("utf-8")
    suffix = f"?{query_string}" if query_string else ""
    return redirect(f"/projetos/{project_id}{suffix}")


def build_project_history_context(project_id):
    """Monta os dados do histórico de ações de um projeto.

    Centraliza a busca do projeto (``get_or_404``) e suas entradas de histórico
    ordenadas (mais recente primeiro). Consumida pelo endpoint JSON da SPA
    (``GET /api/projetos/<id>/historico``) — a antiga rota Jinja
    ``/project/<id>/history`` foi cortada na migração. NÃO faz controle de
    acesso: o chamador valida via ``user_can_access_project`` (403 no envelope).

    Args:
        project_id: ID do projeto cujo histórico será carregado.

    Returns:
        ``dict`` com ``project`` (instância de ``Project``) e ``history`` (lista
        de ``ProjectHistory`` ordenada por ``timestamp`` decrescente).

    Exemplo:
        >>> ctx = build_project_history_context(1)
        >>> ctx["project"].id
        1
    """
    project = get_or_404(Project, project_id)
    history_entries = (
        ProjectHistory.query.filter_by(project_id=project_id)
        .order_by(ProjectHistory.timestamp.desc())
        .all()
    )
    return {"project": project, "history": history_entries}


@main_bp.route("/projects/download")
@login_required
def download_projects_csv():
    """Download CSV com dados dos projetos (apenas admin)."""
    if not g.user.is_admin:
        flash("Acesso restrito a administradores.", "danger")
        return redirect(url_for("main.list_projects"))

    projects = Project.query.order_by(Project.id).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)
    writer.writerow(
        [
            "ID",
            "Nome",
            "Descrição",
            "Processo SEI-RJ",
            "Órgão Responsável",
            "Status",
            "Data Início",
            "Data Fim",
            "Objetivo EEGD",
            "Resultado EEGD",
            "Indicador EEGD",
            "Total de Etapas",
            "Cumprimento (%)",
        ]
    )

    for p in projects:
        data_inicio = (
            p.data_inicio_projeto.strftime("%d/%m/%Y") if p.data_inicio_projeto else ""
        )
        data_fim = p.data_fim_projeto.strftime("%d/%m/%Y") if p.data_fim_projeto else ""
        objetivo = p.objetivo.descricao if p.objetivo else ""
        resultado = p.resultado_esperado.descricao if p.resultado_esperado else ""
        indicadores = "; ".join(
            ip.indicador.descricao for ip in p.indicadores if ip.indicador
        )
        orgao_responsavel = p.orgao_ref.sigla if p.orgao_ref else (p.orgao or "")
        workflow_etapas = p.workflow_etapas
        total_etapas = len(workflow_etapas)
        if total_etapas:
            concluidas = sum(1 for e in workflow_etapas if e.iniciada and e.done)
            cumprimento = f"{round(concluidas * 100 / total_etapas)}%"
        else:
            cumprimento = "0%"
        writer.writerow(
            [
                p.id,
                _safe_csv_text(p.titulo),
                _safe_csv_text(p.short_description),
                _safe_csv_text("; ".join(item.numero for item in p.sei_processes)),
                _safe_csv_text(orgao_responsavel),
                _safe_csv_text(p.status),
                data_inicio,
                data_fim,
                _safe_csv_text(objetivo),
                _safe_csv_text(resultado),
                _safe_csv_text(indicadores),
                total_etapas,
                cumprimento,
            ]
        )

    timestamp = datetime.datetime.now().strftime("%d%m%Y%H%M")
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="projetos{timestamp}.csv"'
    )
    output.close()
    return response
