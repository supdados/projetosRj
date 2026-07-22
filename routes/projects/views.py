import csv
import datetime
import io
from collections import defaultdict

from flask import (
    flash,
    g,
    make_response,
    redirect,
    request,
    url_for,
)

from models import (
    Etapa,
    Project,
    ProjectHistory,
    Task,
    db,
)
from catalogs.abep import ABEP_INDICADORES_OPTIONS
from catalogs.inventario import any_orgao_allows_inventario

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.orgao_scope import (
    expand_orgao_filter_ids,
    get_user_orgao_options,
    get_user_orgao_siglas,
    get_user_orgao_subtree_ids,
    sanitize_orgao_filter_for_current_user,
    user_can_access_project,
)
from services.etapa_positions import build_etapa_position_map
from routes.shared import (
    get_or_404,
    get_goal_catalog_context,
    parse_db_integer_id,
    parse_abep_indicator_filter,
    parse_objetivo_filter,
    project_orgao_search_filter,
)

CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe_csv_text(value):
    text = "" if value is None else str(value)
    if text.lstrip().startswith(CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def build_projects_list_context(
    *,
    selected_priority=None,
    selected_status=None,
    selected_orgao_id=None,
    selected_atraso=None,
    selected_special_project=None,
    selected_delivery_type=None,
    selected_abep_indicator=None,
    selected_objetivo=None,
    search_query="",
    page=1,
):
    """Monta os dados da Lista de Projetos, respeitando o escopo de órgão.

    Centraliza as queries/filtros/paginação que a rota Jinja ``/projects``
    (``list_projects``) usa, para que a rota Jinja e o endpoint JSON da SPA
    (``GET /api/projetos``) compartilhem a MESMA fonte de verdade. O escopo de
    órgão é server-side (não-admin restrito à subárvore). O chamador é
    responsável por sanitizar o filtro de órgão via
    ``sanitize_orgao_filter_for_current_user`` antes de passar
    ``selected_orgao_id``.

    Args:
        selected_priority: Filtro de prioridade (ou ``None``/"").
        selected_status: Filtro de status; o chamador define o default "Vigente"
            (mantido aqui apenas como filtro, sem reescrever o default).
        selected_orgao_id: ID de órgão já validado para o usuário (ou ``None``).
        selected_atraso: "atrasado" | "no_prazo" | "" (filtro aplicado em Python).
        selected_special_project: "ABEP" | "TCE" | "" .
        selected_delivery_type: Tipo de entrega (ou "").
        selected_abep_indicator: Indicador ABEP (normalizado internamente).
        selected_objetivo: ID de objetivo como string (ou "").
        search_query: Texto de busca (título/órgão/indicador/ID).
        page: Página solicitada (1-based) da lista paginada.

    Returns:
        ``dict`` com a lista paginada (``projects``), os filtros
        aplicados/selecionados, as opções de filtro (incluindo ``orgaos_options``
        e ``ABEP_INDICADORES_OPTIONS``) e os metadados de paginação.
    """
    per_page = 40

    query = Project.query

    if not g.user.is_admin:
        user_orgao_subtree_ids = get_user_orgao_subtree_ids(g.user)
        if user_orgao_subtree_ids:
            query = query.filter(Project.orgao_id.in_(user_orgao_subtree_ids))
        else:
            query = query.filter(Project.id == -1)

    if selected_orgao_id is not None:
        subtree_ids = expand_orgao_filter_ids(selected_orgao_id)
        if subtree_ids:
            query = query.filter(Project.orgao_id.in_(subtree_ids))

    if selected_priority and selected_priority != "":
        query = query.filter(Project.prioridade == selected_priority)
    if selected_status and selected_status != "":
        query = query.filter(Project.status == selected_status)
    if selected_special_project and selected_special_project != "":
        query = query.filter(Project.special_project == selected_special_project)
    if selected_delivery_type and selected_delivery_type != "":
        query = query.filter(Project.delivery_type == selected_delivery_type)
    selected_abep_indicator = parse_abep_indicator_filter(selected_abep_indicator)
    if selected_abep_indicator:
        query = query.filter(Project.abep_indicator == selected_abep_indicator)
    objetivo_filter_id = parse_objetivo_filter(selected_objetivo)
    if selected_objetivo and objetivo_filter_id is None:
        selected_objetivo = ""
    if selected_objetivo and objetivo_filter_id is not None:
        query = query.filter(Project.objetivo_id == objetivo_filter_id)

    # Filtro de busca (título, órgão, indicador ABEP)
    if search_query:
        search_pattern = f"%{search_query}%"
        search_id = parse_db_integer_id(search_query)
        text_filters = db.or_(
            Project.titulo.ilike(search_pattern),
            project_orgao_search_filter(search_pattern),
            Project.abep_indicator.ilike(search_pattern),
        )
        query = query.filter(
            db.or_(Project.id == search_id, text_filters)
            if search_id is not None
            else text_filters
        )

    # Aplicar filtros de DB antes de filtrar por atraso (que é feito em Python)
    projects_after_db_filters = query.order_by(Project.id).all()

    # Filtro de Atraso (aplicado em Python)
    if selected_atraso and selected_atraso != "":
        data_atual = datetime.date.today()
        filtered_by_delay = []
        for projeto in projects_after_db_filters:
            if (
                projeto.status == "Vigente"
            ):  # Apenas projetos vigentes são considerados para "atraso" ou "no prazo"
                etapas_atrasadas_count = Etapa.query.filter(
                    Etapa.project_id == projeto.id,
                    Etapa.done == False,
                    Etapa.entry_type != "google_meeting",
                    Etapa.data_fim < data_atual,
                ).count()
                if selected_atraso == "atrasado" and etapas_atrasadas_count > 0:
                    filtered_by_delay.append(projeto)
                elif selected_atraso == "no_prazo" and etapas_atrasadas_count == 0:
                    filtered_by_delay.append(projeto)
        all_projects_filtered = filtered_by_delay
    else:
        all_projects_filtered = projects_after_db_filters

    # Aplicar paginação manualmente (já que alguns filtros são em Python)
    total_projects = len(all_projects_filtered)
    total_pages = (total_projects + per_page - 1) // per_page  # Ceiling division

    # Clampar page fora do intervalo válido (evita slice negativo com page<=0)
    if total_pages == 0:
        page = 1
    else:
        page = max(1, min(page or 1, total_pages))

    # Calcular índices para slice
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    # Paginar os projetos
    projects_paginated = all_projects_filtered[start_idx:end_idx]

    options_query = Project.query
    if not g.user.is_admin:
        user_orgao_subtree_ids = get_user_orgao_subtree_ids(g.user)
        if user_orgao_subtree_ids:
            options_query = options_query.filter(
                Project.orgao_id.in_(user_orgao_subtree_ids)
            )
        else:
            options_query = options_query.filter(Project.id == -1)

    scoped_option_projects = options_query.all()
    priorities_options = sorted(
        {p.prioridade for p in scoped_option_projects if p.prioridade}
    )
    statuses_options = sorted({p.status for p in scoped_option_projects if p.status})
    atrasos_options = [("no_prazo", "No prazo"), ("atrasado", "Atrasado")]
    objetivos, _, _ = (
        get_goal_catalog_context()
    )  # Para o modal de adicionar projeto e filtro

    # Novas opções para filtros
    special_projects_options = ["ABEP", "TCE"]
    if g.user.is_admin or any_orgao_allows_inventario(get_user_orgao_siglas(g.user)):
        special_projects_options.append("Inventário")
    delivery_types_options = [
        "Sistema",
        "Painel",
        "Norma",
        "Instrumento de parceria",
        "Fluxo Processual",
        "Outro",
    ]
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

    # Subárvore de órgãos visível ao usuário (escopo server-side) para popular o
    # <select> de filtro de órgão na SPA. O template Jinja não usa esta chave (a
    # topnav já injeta a árvore via context processor); fica disponível para o
    # endpoint JSON sem alterar o comportamento renderizado.
    orgaos_options = get_user_orgao_options(g.user)

    return {
        "projects": projects_paginated,
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
        "selected_orgao": selected_orgao_id,
        "priorities": priorities_options,
        "statuses": statuses_options,
        "atrasos_options": atrasos_options,
        "objetivos": objetivos,
        "orgaos_options": orgaos_options,
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
    selected_orgao_id,
    *,
    filtro_periodo="atrasados",
    selected_responsavel="",
    selected_priority="",
    search_query="",
    pending_page=1,
):
    """Monta os dados da tela "Projetos Pendentes", respeitando o escopo de órgão.

    Centraliza queries/agregações num único lugar para o endpoint JSON da SPA
    (``GET /api/projetos-pendentes``) — sucessor da extinta rota Jinja
    ``/projetos_pendentes`` — sem recalcular buckets/contadores no cliente. A
    autorização por órgão é server-side: usuários não-admin ficam restritos à
    sua subárvore (``orgao_scope``).

    Args:
        selected_orgao_id: ID do órgão já validado/sanitizado para o usuário
            corrente (``None`` quando nenhum filtro está aplicado). O chamador é
            responsável por sanitizar via
            ``sanitize_orgao_filter_for_current_user``.
        filtro_periodo: Janela de visibilidade ("atrasados" | "7dias" | "14dias"
            | "21dias"); valores fora do conjunto caem para "atrasados".
        selected_responsavel: Filtro de responsável (substring, case-insensitive).
        pending_page: Página solicitada (1-based) da lista paginada de projetos.

    Returns:
        ``dict`` com a lista paginada (``projetos_com_etapas``), os mapas de
        bucket/progresso, os contadores agregados e os metadados de paginação,
        consumidos pelo serializer do endpoint JSON da SPA.

    Exemplo:
        >>> ctx = build_projetos_pendentes_context(None)
        >>> ctx["summary_counts"]["total_projects"]
        3
    """
    pending_per_page = 15

    valid_periods = {"atrasados", "7dias", "14dias", "21dias"}
    if filtro_periodo not in valid_periods:
        filtro_periodo = "atrasados"

    data_atual = datetime.date.today()
    data_7_dias = data_atual + datetime.timedelta(days=7)
    data_14_dias = data_atual + datetime.timedelta(days=14)
    data_21_dias = data_atual + datetime.timedelta(days=21)

    def resolve_reference_date(etapa):
        return etapa.data_inicio if etapa.data_inicio else etapa.data_fim

    def classify_bucket(etapa):
        reference_date = resolve_reference_date(etapa)
        if not reference_date:
            return "sem_data"
        if reference_date < data_atual:
            return "atrasada"
        if reference_date <= data_7_dias:
            return "7dias"
        if reference_date <= data_14_dias:
            return "14dias"
        if reference_date <= data_21_dias:
            return "21dias"
        return "futuro"

    visible_buckets_by_period = {
        "atrasados": {"atrasada"},
        "7dias": {"atrasada", "7dias"},
        "14dias": {"atrasada", "7dias", "14dias"},
        "21dias": {"atrasada", "7dias", "14dias", "21dias"},
    }
    visible_buckets = visible_buckets_by_period[filtro_periodo]

    query_projetos_base = Project.query.filter(Project.status == "Vigente")

    if not g.user.is_admin:
        user_orgao_subtree_ids = get_user_orgao_subtree_ids(g.user)
        if user_orgao_subtree_ids:
            query_projetos_base = query_projetos_base.filter(
                Project.orgao_id.in_(user_orgao_subtree_ids)
            )
        else:
            query_projetos_base = query_projetos_base.filter(Project.id == -1)

    if selected_orgao_id is not None:
        orgao_subtree = expand_orgao_filter_ids(selected_orgao_id)
        if orgao_subtree:
            query_projetos_base = query_projetos_base.filter(
                Project.orgao_id.in_(orgao_subtree)
            )

    # Filtro de prioridade e busca textual (paridade com a tela de Projetos):
    # restringem o conjunto de projetos vigentes ANTES do cálculo de buckets.
    if selected_priority:
        query_projetos_base = query_projetos_base.filter(
            Project.prioridade == selected_priority
        )

    if search_query:
        search_pattern = f"%{search_query}%"
        search_id = parse_db_integer_id(search_query)
        text_filters = db.or_(
            Project.titulo.ilike(search_pattern),
            project_orgao_search_filter(search_pattern),
            Project.abep_indicator.ilike(search_pattern),
        )
        query_projetos_base = query_projetos_base.filter(
            db.or_(Project.id == search_id, text_filters)
            if search_id is not None
            else text_filters
        )

    projetos_vigentes = query_projetos_base.order_by(Project.titulo.asc()).all()
    project_ids = [p.id for p in projetos_vigentes]

    objetivos, _, _ = get_goal_catalog_context()

    # Subárvore de órgãos visível ao usuário (escopo server-side) para popular o
    # <select> de filtro de órgão na SPA. A árvore é a mesma usada pela topnav;
    # aqui só repassamos os nós (a serialização em opções fica no endpoint JSON).
    orgaos_options = get_user_orgao_options(g.user)

    if not project_ids:
        return {
            "projetos_com_etapas": [],
            "objetivos": objetivos,
            "orgaos_options": orgaos_options,
            "selected_orgao": selected_orgao_id,
            "filtro_periodo": filtro_periodo,
            "selected_responsavel": selected_responsavel,
            "selected_priority": selected_priority,
            "search_query": search_query,
            "responsaveis_options": [],
            "period_options": [
                ("atrasados", "Projetos Atrasados"),
                ("7dias", "Próximos 7 Dias"),
                ("14dias", "Próximos 14 Dias"),
                ("21dias", "Próximos 21 Dias"),
            ],
            "period_label_map": {
                "atrasados": "Atrasados",
                "7dias": "Próximos 7 Dias",
                "14dias": "Próximos 14 Dias",
                "21dias": "Próximos 21 Dias",
            },
            "etapa_bucket_map": {},
            "etapa_position_map": {},
            "etapa_task_progress": {},
            "summary_counts": {
                "total_projects": 0,
                "atrasada": 0,
                "7dias": 0,
                "14dias": 0,
                "21dias": 0,
                "sem_data": 0,
            },
            "pending_page": 1,
            "pending_total_pages": 0,
            "pending_per_page": pending_per_page,
            "pending_total_projects": 0,
        }

    responsaveis_query = (
        Etapa.query.filter(
            Etapa.project_id.in_(project_ids),
            Etapa.done.is_(False),
            Etapa.entry_type != "google_meeting",
            Etapa.responsavel.isnot(None),
        )
        .with_entities(Etapa.responsavel)
        .distinct()
        .all()
    )
    # set(): o DISTINCT roda no banco ANTES do strip — "SUPIM" e "SUPIM " viram
    # duplicatas exatas após o trim, e a SPA quebra com chave duplicada no
    # {#each} do filtro de responsável (each_key_duplicate).
    responsaveis_options = sorted(
        {r[0].strip() for r in responsaveis_query if r[0] and r[0].strip()},
        key=lambda value: value.casefold(),
    )

    etapas_query = Etapa.query.filter(
        Etapa.project_id.in_(project_ids),
        Etapa.done.is_(False),
        Etapa.entry_type != "google_meeting",
    )
    if selected_responsavel:
        etapas_query = etapas_query.filter(
            Etapa.responsavel.ilike(f"%{selected_responsavel}%")
        )

    etapas_abertas = etapas_query.order_by(
        Etapa.project_id.asc(),
        Etapa.ordem.asc(),
        Etapa.id.asc(),
    ).all()

    # Progresso de tarefas (concluídas / total) por etapa aberta — exibido na
    # pílula "Tarefas" de cada linha, no mesmo formato "3/10" da tela do projeto.
    etapa_ids_abertas = [etapa.id for etapa in etapas_abertas]
    if etapa_ids_abertas:
        total_task_counts = dict(
            db.session.query(Task.etapa_id, db.func.count(Task.id))
            .filter(
                Task.etapa_id.in_(etapa_ids_abertas),
                Task.is_archived.is_(False),
            )
            .group_by(Task.etapa_id)
            .all()
        )
        done_task_counts = dict(
            db.session.query(Task.etapa_id, db.func.count(Task.id))
            .filter(
                Task.etapa_id.in_(etapa_ids_abertas),
                Task.is_archived.is_(False),
                Task.status == "finalizada",
            )
            .group_by(Task.etapa_id)
            .all()
        )
    else:
        total_task_counts = {}
        done_task_counts = {}
    etapa_task_progress = {
        etapa_id: {
            "total": int(total_task_counts.get(etapa_id, 0)),
            "done": int(done_task_counts.get(etapa_id, 0)),
        }
        for etapa_id in etapa_ids_abertas
    }

    etapas_por_projeto = defaultdict(list)
    etapa_bucket_map = {}
    summary_counts = {
        "total_projects": 0,
        "atrasada": 0,
        "7dias": 0,
        "14dias": 0,
        "21dias": 0,
        "sem_data": 0,
    }

    for etapa in etapas_abertas:
        bucket = classify_bucket(etapa)
        etapa_bucket_map[etapa.id] = bucket
        etapas_por_projeto[etapa.project_id].append(etapa)
        if bucket in summary_counts:
            summary_counts[bucket] += 1

    projetos_pendentes_com_etapas = []
    project_by_id = {p.id: p for p in projetos_vigentes}

    for project_id, etapas_project in etapas_por_projeto.items():
        projeto = project_by_id.get(project_id)
        if not projeto:
            continue

        etapas_project_sorted = sorted(
            etapas_project,
            key=lambda etapa: (
                etapa.data_fim is None,
                etapa.data_fim or datetime.date.max,
                etapa.data_inicio is None,
                etapa.data_inicio or datetime.date.max,
                etapa.ordem if etapa.ordem is not None else 10**9,
                etapa.id,
            ),
        )

        etapas_visiveis = []
        etapas_outras = []
        counts = {
            "qtd_atrasadas": 0,
            "bucket_7dias": 0,
            "bucket_14dias": 0,
            "bucket_21dias": 0,
            "qtd_sem_data": 0,
        }
        max_overdue_days = 0

        for etapa in etapas_project_sorted:
            bucket = etapa_bucket_map.get(etapa.id, "futuro")

            if bucket == "atrasada":
                counts["qtd_atrasadas"] += 1
                reference_date = resolve_reference_date(etapa)
                if reference_date:
                    overdue_days = (data_atual - reference_date).days
                    if overdue_days > max_overdue_days:
                        max_overdue_days = overdue_days
            elif bucket == "7dias":
                counts["bucket_7dias"] += 1
            elif bucket == "14dias":
                counts["bucket_14dias"] += 1
            elif bucket == "21dias":
                counts["bucket_21dias"] += 1
            elif bucket == "sem_data":
                counts["qtd_sem_data"] += 1

            if bucket in visible_buckets:
                etapas_visiveis.append(etapa)
            else:
                etapas_outras.append(etapa)

        if not etapas_visiveis:
            continue

        qtd_7dias = counts["bucket_7dias"]
        qtd_14dias = counts["bucket_7dias"] + counts["bucket_14dias"]
        qtd_21dias = (
            counts["bucket_7dias"] + counts["bucket_14dias"] + counts["bucket_21dias"]
        )

        projetos_pendentes_com_etapas.append(
            {
                "projeto": projeto,
                "etapas_visiveis": etapas_visiveis,
                "etapas_outras": etapas_outras,
                "qtd_visiveis": len(etapas_visiveis),
                "qtd_outras": len(etapas_outras),
                "qtd_atrasadas": counts["qtd_atrasadas"],
                "qtd_7dias": qtd_7dias,
                "qtd_14dias": qtd_14dias,
                "qtd_21dias": qtd_21dias,
                "qtd_sem_data": counts["qtd_sem_data"],
                "max_overdue_days": max_overdue_days,
            }
        )

    projetos_pendentes_com_etapas.sort(
        key=lambda item: (
            -item["max_overdue_days"],
            -item["qtd_visiveis"],
            (item["projeto"].titulo or "").casefold(),
        )
    )
    pending_total_projects = len(projetos_pendentes_com_etapas)
    summary_counts["total_projects"] = pending_total_projects

    pending_total_pages = (
        (pending_total_projects + pending_per_page - 1) // pending_per_page
        if pending_total_projects > 0
        else 0
    )
    if pending_total_pages == 0:
        pending_page = 1
    else:
        pending_page = max(1, min(pending_page or 1, pending_total_pages))

    start_idx = (pending_page - 1) * pending_per_page
    end_idx = start_idx + pending_per_page
    projetos_pendentes_paginated = projetos_pendentes_com_etapas[start_idx:end_idx]

    etapa_position_map = build_etapa_position_map(
        [item["projeto"].id for item in projetos_pendentes_paginated]
    )

    return {
        "projetos_com_etapas": projetos_pendentes_paginated,
        "objetivos": objetivos,
        "orgaos_options": orgaos_options,
        "selected_orgao": selected_orgao_id,
        "filtro_periodo": filtro_periodo,
        "selected_responsavel": selected_responsavel,
        "selected_priority": selected_priority,
        "search_query": search_query,
        "responsaveis_options": responsaveis_options,
        "period_options": [
            ("atrasados", "Projetos Atrasados"),
            ("7dias", "Próximos 7 Dias"),
            ("14dias", "Próximos 14 Dias"),
            ("21dias", "Próximos 21 Dias"),
        ],
        "period_label_map": {
            "atrasados": "Atrasados",
            "7dias": "Próximos 7 Dias",
            "14dias": "Próximos 14 Dias",
            "21dias": "Próximos 21 Dias",
        },
        "etapa_bucket_map": etapa_bucket_map,
        "etapa_position_map": etapa_position_map,
        "etapa_task_progress": etapa_task_progress,
        "summary_counts": summary_counts,
        "pending_page": pending_page,
        "pending_total_pages": pending_total_pages,
        "pending_per_page": pending_per_page,
        "pending_total_projects": pending_total_projects,
    }


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
