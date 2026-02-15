from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, g, send_from_directory
import datetime
import os
from functools import wraps
from zoneinfo import ZoneInfo
from models import db, User, Project, Etapa, IndicadorProjeto, StageTemplate, StageTemplateItem, UserArea, ProjectHistory, Task, TaskItem, TaskItemComment
from sqlalchemy.orm import joinedload
from sqlalchemy import text, or_, and_, case, func
from objective_catalog import (
    OBJETIVO_IDS,
    RESULTADO_IDS,
    get_objetivos_choices,
    get_resultados_por_objetivo,
    get_indicadores_por_resultado,
    get_resultados_for_objetivo,
    get_indicadores_for_resultado,
    normalize_goal_selection,
    sync_goal_catalog_to_db,
)
from abep_catalog import ABEP_INDICADORES_OPTIONS, normalize_abep_indicator

main_bp = Blueprint('main', __name__)

# Fuso Brasil para respostas JSON (comentários, etc.)
TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')

def format_local_time(dt, fmt='%d/%m %H:%M'):
    """Converte datetime UTC (naive) para horário do Brasil e retorna string."""
    if dt is None:
        return None
    utc = dt.replace(tzinfo=ZoneInfo('UTC')) if dt.tzinfo is None else dt
    return utc.astimezone(TIMEZONE_BR).strftime(fmt)

# Constante para as opções de áreas (pode ser movida para um config ou detectada do DB no futuro)
AREAS_RESPONSAVEIS_CHOICES = ["Auditoria", "CHEGAB", "SUPDADOS", "SUBDGD", "SUPEST", "SUPIM", "SUPPAE", "PRODERJ", "ASSESP", "ECENTRAL", "SUBEDD", "VPD", "VPE", "VPT"]

# Função helper para registrar histórico de ações
def log_project_action(project_id, action_type, description, old_value=None, new_value=None):
    """
    Registra uma ação no histórico do projeto
    
    Args:
        project_id: ID do projeto
        action_type: Tipo da ação ('create', 'edit', 'delete', 'add_etapa', etc)
        description: Descrição legível da ação
        old_value: Valor anterior (opcional)
        new_value: Novo valor (opcional)
    """
    try:
        history_entry = ProjectHistory(
            project_id=project_id,
            user_id=g.user.id,
            action_type=action_type,
            action_description=description,
            old_value=old_value,
            new_value=new_value
        )
        db.session.add(history_entry)
        # Não fazemos commit aqui - será feito pela função que chamou
    except Exception as e:
        print(f"Erro ao registrar histórico: {e}")
        # Não interrompe a operação principal se o log falhar


def get_goal_catalog_context():
    """Retorna estruturas de objetivo/resultado/indicador vindas do catalogo canonico."""
    return (
        get_objetivos_choices(),
        get_resultados_por_objetivo(),
        get_indicadores_por_resultado(),
    )


def parse_objetivo_filter(raw_value):
    if not raw_value:
        return None
    try:
        objetivo_id = int(raw_value)
    except (TypeError, ValueError):
        return None
    if objetivo_id not in OBJETIVO_IDS:
        return None
    return objetivo_id


def parse_abep_indicator_filter(raw_value):
    if not raw_value:
        return None
    try:
        normalized = normalize_abep_indicator(raw_value)
    except ValueError:
        return None
    return normalized


GLOBAL_SEARCH_DEFAULT_LIMIT = 5
GLOBAL_SEARCH_API_MAX_LIMIT = 20
GLOBAL_SEARCH_PAGE_LIMIT = 50


def _truncate_text(value, max_length=140):
    text_value = " ".join((value or "").split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + "..."


def _build_match_excerpt(value, term, max_length=110):
    text_value = " ".join((value or "").split())
    if not text_value:
        return ""

    normalized_term = (term or "").strip().lower()
    if not normalized_term:
        return _truncate_text(text_value, max_length)

    lowered_value = text_value.lower()
    match_index = lowered_value.find(normalized_term)
    if match_index == -1:
        return _truncate_text(text_value, max_length)

    context_before = max_length // 3
    start = max(0, match_index - context_before)
    end = min(len(text_value), start + max_length)
    snippet = text_value[start:end].strip()

    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text_value):
        snippet = f"{snippet}..."
    return snippet


def _resolve_match_info(term, ordered_fields):
    normalized_term = (term or "").strip().lower()
    if not normalized_term:
        return {
            "match_field": "",
            "match_label": "",
            "match_excerpt": ""
        }

    for field_name, field_label, field_value in ordered_fields:
        normalized_value = " ".join((field_value or "").split())
        if not normalized_value:
            continue
        if normalized_term in normalized_value.lower():
            return {
                "match_field": field_name,
                "match_label": field_label,
                "match_excerpt": _build_match_excerpt(normalized_value, term),
            }

    return {
        "match_field": "",
        "match_label": "",
        "match_excerpt": ""
    }


def _empty_global_search_payload(term):
    normalized = (term or "").strip()
    return {
        "query": normalized,
        "counts": {
            "projects": 0,
            "stages": 0,
            "tasks": 0,
            "task_items": 0,
            "total": 0
        },
        "results": {
            "projects": [],
            "stages": [],
            "tasks": [],
            "task_items": []
        }
    }


def _normalize_global_search_limit(raw_limit, default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT, max_limit=GLOBAL_SEARCH_API_MAX_LIMIT):
    if raw_limit is None or raw_limit == "":
        return default_limit
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        return default_limit
    return max(1, min(parsed, max_limit))


def build_global_search_results(term, user, limit_per_type=None):
    normalized_term = (term or "").strip()
    if not normalized_term:
        return _empty_global_search_payload(normalized_term)

    search_pattern = f"%{normalized_term}%"
    prefix_pattern = f"{normalized_term.lower()}%"
    status_labels = {
        "programado": "Programado",
        "em_andamento": "Em andamento",
        "validacao": "Validacao",
        "finalizado": "Finalizado",
    }

    user_areas = user.get_areas() if (user and not user.is_admin) else []

    def apply_optional_limit(query):
        if limit_per_type is not None:
            return query.limit(limit_per_type)
        return query

    def prefix_order_for(column):
        return case(
            (func.lower(func.coalesce(column, "")).like(prefix_pattern), 0),
            else_=1
        )

    project_query = Project.query.filter(
        or_(
            Project.titulo.ilike(search_pattern),
            Project.orgao.ilike(search_pattern),
            Project.short_description.ilike(search_pattern),
            Project.observacao.ilike(search_pattern),
            Project.area_responsavel.ilike(search_pattern),
        )
    )
    if not user.is_admin:
        if user_areas:
            project_query = project_query.filter(Project.area_responsavel.in_(user_areas))
        else:
            project_query = project_query.filter(Project.id == -1)
    project_query = apply_optional_limit(
        project_query.order_by(prefix_order_for(Project.titulo), Project.id.desc())
    )
    projects = project_query.all()

    stage_query = Etapa.query.join(Project, Etapa.project_id == Project.id).options(joinedload(Etapa.project)).filter(
        or_(
            Etapa.descricao.ilike(search_pattern),
            Etapa.comentarios.ilike(search_pattern),
            Etapa.responsavel.ilike(search_pattern),
        )
    )
    if not user.is_admin:
        if user_areas:
            stage_query = stage_query.filter(Project.area_responsavel.in_(user_areas))
        else:
            stage_query = stage_query.filter(Project.id == -1)
    stage_query = apply_optional_limit(
        stage_query.order_by(prefix_order_for(Etapa.descricao), Etapa.id.desc())
    )
    stages = stage_query.all()

    task_query = Task.query.outerjoin(Project, Task.project_id == Project.id).options(joinedload(Task.project)).filter(
        Task.titulo.ilike(search_pattern)
    )
    if not user.is_admin:
        task_query = task_query.filter(
            or_(
                and_(Task.project_id.isnot(None), Project.area_responsavel.in_(user_areas)),
                and_(Task.project_id.is_(None), Task.created_by_id == user.id)
            )
        )
    task_query = apply_optional_limit(
        task_query.order_by(prefix_order_for(Task.titulo), Task.id.desc())
    )
    tasks = task_query.all()

    task_item_query = TaskItem.query.join(Task, TaskItem.task_id == Task.id).outerjoin(
        Project, Task.project_id == Project.id
    ).options(
        joinedload(TaskItem.task).joinedload(Task.project)
    ).filter(
        or_(
            TaskItem.descricao.ilike(search_pattern),
            TaskItem.responsavel.ilike(search_pattern),
        )
    )
    if not user.is_admin:
        task_item_query = task_item_query.filter(
            or_(
                and_(Task.project_id.isnot(None), Project.area_responsavel.in_(user_areas)),
                and_(Task.project_id.is_(None), Task.created_by_id == user.id)
            )
        )
    task_item_query = apply_optional_limit(
        task_item_query.order_by(prefix_order_for(TaskItem.descricao), TaskItem.id.desc())
    )
    task_items = task_item_query.all()

    project_results = [
        {
            "type": "project",
            "type_label": "Projeto",
            "title": _truncate_text(project.titulo or f"Projeto #{project.id}", 120),
            "subtitle": f"Orgao: {_truncate_text(project.orgao, 90)}" if project.orgao else "",
            "meta": f"Area: {project.area_responsavel}" if project.area_responsavel else "Area nao informada",
            "url": url_for('main.project_detail', project_id=project.id),
            **_resolve_match_info(normalized_term, [
                ("titulo", "Titulo", project.titulo),
                ("orgao", "Orgao", project.orgao),
                ("short_description", "Descricao curta", project.short_description),
                ("observacao", "Observacao", project.observacao),
                ("area_responsavel", "Area", project.area_responsavel),
            ]),
        }
        for project in projects
    ]

    stage_results = []
    for stage in stages:
        project = stage.project
        stage_match = _resolve_match_info(normalized_term, [
            ("descricao", "Descricao", stage.descricao),
            ("comentarios", "Comentario", stage.comentarios),
            ("responsavel", "Responsavel", stage.responsavel),
        ])
        stage_results.append({
            "type": "stage",
            "type_label": "Etapa",
            "title": _truncate_text(stage.descricao or f"Etapa #{stage.id}", 120),
            "subtitle": f"Projeto: {_truncate_text(project.titulo, 95)}" if project else "",
            "meta": (
                f"Responsavel: {_truncate_text(stage.responsavel, 80)}"
                if stage.responsavel else
                "Responsavel nao informado"
            ),
            "url": url_for('main.project_detail', project_id=stage.project_id, focus_etapa=stage.id),
            **stage_match,
        })

    task_results = []
    for task in tasks:
        task_match = _resolve_match_info(normalized_term, [
            ("titulo", "Titulo", task.titulo),
        ])
        task_results.append({
            "type": "task",
            "type_label": "Tarefa",
            "title": _truncate_text(task.titulo or f"Tarefa #{task.id}", 120),
            "subtitle": f"Projeto: {_truncate_text(task.project.titulo, 95)}" if task.project else "Sem projeto",
            "meta": (
                f"Criada em {task.created_at.strftime('%d/%m/%Y')}"
                if task.created_at else
                ""
            ),
            "url": url_for('main.task_detail', task_id=task.id),
            **task_match,
        })

    task_item_results = []
    for task_item in task_items:
        task_item_task = task_item.task
        task_item_match = _resolve_match_info(normalized_term, [
            ("descricao", "Descricao", task_item.descricao),
            ("responsavel", "Responsavel", task_item.responsavel),
        ])
        status_label = status_labels.get(task_item.status, task_item.status or "")
        task_item_meta_parts = []
        if status_label:
            task_item_meta_parts.append(f"Status: {status_label}")
        if task_item.responsavel:
            task_item_meta_parts.append(f"Responsavel: {_truncate_text(task_item.responsavel, 80)}")
        task_item_results.append({
            "type": "task_item",
            "type_label": "Item",
            "title": _truncate_text(task_item.descricao or f"Item #{task_item.id}", 120),
            "subtitle": (
                f"Tarefa: {_truncate_text(task_item_task.titulo, 95)}"
                if task_item_task else
                ""
            ),
            "meta": " | ".join(task_item_meta_parts),
            "url": url_for('main.task_detail', task_id=task_item.task_id, focus_item=task_item.id),
            **task_item_match,
        })

    counts = {
        "projects": len(project_results),
        "stages": len(stage_results),
        "tasks": len(task_results),
        "task_items": len(task_item_results),
    }
    counts["total"] = counts["projects"] + counts["stages"] + counts["tasks"] + counts["task_items"]

    return {
        "query": normalized_term,
        "counts": counts,
        "results": {
            "projects": project_results,
            "stages": stage_results,
            "tasks": task_results,
            "task_items": task_item_results,
        }
    }


# Rota específica para servir o favicon
@main_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(main_bp.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


# --- Decorators de Autenticação/Autorização ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: # Verifica se o user_id está na sessão
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('main.login_page', next=request.url))
        # g.user é carregado em app.py via @app.before_request
        if not g.user: # Verifica se o objeto g.user foi carregado (ou seja, usuário existe no DB)
            session.clear() # Limpa sessão inválida
            flash('Sua sessão é inválida ou o usuário não existe. Por favor, faça login novamente.', 'warning')
            return redirect(url_for('main.login_page'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # g.user deve existir por causa do @login_required que geralmente vem antes
        if not g.user or not g.user.is_admin:
            flash('Você não tem permissão para acessar esta página.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Processador de contexto para injetar o ano atual e áreas responsáveis (a função em si)
# O registro dela no app é feito em app.py
def inject_current_year():
    return {
        'current_year': datetime.datetime.utcnow().year,
        'AREAS_RESPONSAVEIS_CHOICES': AREAS_RESPONSAVEIS_CHOICES,
        'ABEP_INDICADORES_OPTIONS': ABEP_INDICADORES_OPTIONS
    }


@main_bp.route('/', methods=['GET'])
def home():
    if 'user_id' in session and g.user: # Se logado e usuário válido
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login_page'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if 'user_id' in session and g.user: # Se já logado e usuário válido
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Usuário e senha são obrigatórios.', 'warning')
            # Não precisa passar 'error' aqui, o flash já cuida da mensagem
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear() # Limpa qualquer sessão antiga
            session['user_id'] = user.id
            # Outras informações como username, nome, is_admin, area, orgao
            # serão primariamente acessadas via g.user (carregado no @app.before_request)
            # ou pelo context_processor que injeta current_user_obj e is_admin_user.
            # Não é estritamente necessário colocar tudo na session se g.user está disponível.
            
            g.user = user # Garante que g.user esteja populado para este request imediato

            flash(f'Login bem-sucedido, {user.name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            flash('Credenciais inválidas. Tente novamente.', 'danger')
            # Não precisa passar 'error' aqui, o flash já cuida da mensagem
            return render_template('login.html')
    return render_template('login.html')

@main_bp.route('/logout')
@login_required # Só pode fazer logout se estiver logado
def logout():
    session.clear()
    g.user = None # Limpa g.user também
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('main.login_page'))

@main_bp.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')

        if not current_password or not new_password or not confirm_new_password:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('change_password.html')

        if not g.user.check_password(current_password):
            flash('Senha atual incorreta.', 'danger')
            return render_template('change_password.html')

        if new_password != confirm_new_password:
            flash('A nova senha e a confirmação não correspondem.', 'danger')
            return render_template('change_password.html')
        
        if len(new_password) < 6:
            flash('A nova senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('change_password.html')

        g.user.set_password(new_password)
        db.session.commit()
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('change_password.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    project_query_base = Project.query
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if user_areas:
            project_query_base = project_query_base.filter(Project.area_responsavel.in_(user_areas))

    recent_projects = project_query_base.order_by(Project.id.desc()).limit(9).all()
    
    def count_projects_for_user(filter_expression=None):
        query = Project.query
        if not g.user.is_admin:
            user_areas = g.user.get_areas()
            if user_areas:
                query = query.filter(Project.area_responsavel.in_(user_areas))
        if filter_expression is not None: # Permite SQLAlchemy filter expressions
            query = query.filter(filter_expression)
        return query.count()

    count_urgente = count_projects_for_user(Project.prioridade == 'urgente')
    count_alta = count_projects_for_user(Project.prioridade == 'alta')
    count_media = count_projects_for_user(Project.prioridade == 'media')
    count_baixa = count_projects_for_user(Project.prioridade == 'baixa')
    count_vigente = count_projects_for_user(Project.status == 'Vigente')
    count_finalizado = count_projects_for_user(Project.status == 'Finalizado')
    num_projects = count_projects_for_user()
    
    data_atual = datetime.date.today() # Usar datetime.date.today() é mais simples
    projetos_em_atraso = 0
    
    projetos_vigentes_query = Project.query.filter(Project.status == 'Vigente')
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if user_areas:
            projetos_vigentes_query = projetos_vigentes_query.filter(Project.area_responsavel.in_(user_areas))
    
    for projeto in projetos_vigentes_query.all():
        if Etapa.query.filter(Etapa.project_id == projeto.id, Etapa.done == False, Etapa.data_fim < data_atual).count() > 0:
            projetos_em_atraso += 1
            
    objetivos, _, _ = get_goal_catalog_context()
    
    return render_template(
        'index.html', 
        recent_projects=recent_projects,
        count_urgente=count_urgente, count_alta=count_alta,
        count_media=count_media, count_baixa=count_baixa,
        count_vigente=count_vigente, count_finalizado=count_finalizado, num_projects=num_projects,
        projetos_em_atraso=projetos_em_atraso,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES # Para o modal
    )


@main_bp.route('/api/busca-global', methods=['GET'])
@login_required
def global_search_api():
    search_term = (request.args.get('q') or '').strip()
    limit_per_type = _normalize_global_search_limit(
        request.args.get('limit'),
        default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT,
        max_limit=GLOBAL_SEARCH_API_MAX_LIMIT
    )

    if len(search_term) < 2:
        return jsonify(_empty_global_search_payload(search_term))

    payload = build_global_search_results(search_term, g.user, limit_per_type=limit_per_type)
    return jsonify(payload)


@main_bp.route('/busca', methods=['GET'])
@login_required
def global_search_page():
    search_term = (request.args.get('q') or '').strip()
    if search_term:
        search_payload = build_global_search_results(
            search_term,
            g.user,
            limit_per_type=GLOBAL_SEARCH_PAGE_LIMIT
        )
    else:
        search_payload = _empty_global_search_payload(search_term)

    return render_template(
        'search_results.html',
        search_query=search_term,
        search_payload=search_payload
    )

@main_bp.route('/projects')
@login_required
def list_projects():
    selected_priority = request.args.get('prioridade')
    selected_status = request.args.get('status')
    selected_area_filter = request.args.get('area') # Filtro de área do formulário
    selected_atraso = request.args.get('atraso')
    selected_special_project = request.args.get('special_project')  # Novo filtro
    selected_delivery_type = request.args.get('delivery_type')  # Novo filtro
    selected_abep_indicator = request.args.get('abep_indicator')  # Novo filtro
    selected_objetivo = request.args.get('objetivo')  # Novo filtro
    search_query = request.args.get('search', '').strip()  # Busca
    
    # Paginação
    page = request.args.get('page', 1, type=int)
    per_page = 40

    # Se nenhum status for especificado na URL, define 'Vigente' como padrão.
    # A verificação `is None` é importante para permitir que o usuário selecione
    # "Todos os status", que envia uma string vazia ("").
    if selected_status is None:
        selected_status = 'Vigente'

    query = Project.query

    # Filtro de área baseado no perfil do usuário E no filtro do formulário
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if user_areas:
            # Usuário não-admin com áreas: filtra pelas suas áreas
            query = query.filter(Project.area_responsavel.in_(user_areas))
            # Se o usuário aplicou um filtro de área e essa área está nas suas áreas, aplica o filtro
            if selected_area_filter and selected_area_filter in user_areas:
                query = query.filter(Project.area_responsavel == selected_area_filter)
            # Se não, mostra todas as suas áreas (já filtrado acima)
    elif selected_area_filter and selected_area_filter != "": # Admin pode filtrar por qualquer área
        query = query.filter(Project.area_responsavel == selected_area_filter)
    # Se for admin e não houver filtro de área, mostra todas as áreas.

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
    
    # Filtro de busca (título, área, órgão, indicador ABEP)
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Project.titulo.ilike(search_pattern),
                Project.area_responsavel.ilike(search_pattern),
                Project.orgao.ilike(search_pattern),
                Project.abep_indicator.ilike(search_pattern)
            )
        )
        
    # Aplicar filtros de DB antes de filtrar por atraso (que é feito em Python)
    projects_after_db_filters = query.order_by(Project.id).all()
    
    # Filtro de Atraso (aplicado em Python)
    if selected_atraso and selected_atraso != "":
        data_atual = datetime.date.today()
        filtered_by_delay = []
        for projeto in projects_after_db_filters:
            if projeto.status == 'Vigente': # Apenas projetos vigentes são considerados para "atraso" ou "no prazo"
                etapas_atrasadas_count = Etapa.query.filter(
                    Etapa.project_id == projeto.id,
                    Etapa.done == False,
                    Etapa.data_fim < data_atual
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
    
    # Calcular índices para slice
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Paginar os projetos
    projects_paginated = all_projects_filtered[start_idx:end_idx]
    
    # Opções para os dropdowns de filtro
    # Áreas: se não for admin, suas áreas (se tiver). Se admin, todas as áreas com projetos + áreas padrão.
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        areas_options_for_dropdown = sorted(user_areas) if user_areas else []
    else:
        project_areas_in_db = set(p.area_responsavel for p in Project.query.all() if p.area_responsavel)
        areas_options_for_dropdown = sorted(list(project_areas_in_db.union(set(AREAS_RESPONSAVEIS_CHOICES))))

    priorities_options = sorted(list(set(p.prioridade for p in Project.query.all() if p.prioridade)))
    statuses_options = sorted(list(set(p.status for p in Project.query.all() if p.status)))
    atrasos_options = [("no_prazo", "No prazo"), ("atrasado", "Atrasado")]
    objetivos, _, _ = get_goal_catalog_context()  # Para o modal de adicionar projeto e filtro
    
    # Novas opções para filtros
    special_projects_options = ['ABEP', 'TCE']
    delivery_types_options = ['Sistema', 'Painel', 'Norma', 'Instrumento de parceria', 'Fluxo Processual', 'Outro']

    # Verificar se há filtros ativos (para mostrar botão "Limpar")
    has_active_filters = False
    if search_query:
        has_active_filters = True
    if selected_priority:
        has_active_filters = True
    if selected_status and selected_status != 'Vigente':  # Vigente é o padrão
        has_active_filters = True
    if selected_atraso:
        has_active_filters = True
    if selected_special_project:
        has_active_filters = True
    if selected_delivery_type:
        has_active_filters = True
    if selected_abep_indicator:
        has_active_filters = True
    if selected_objetivo:
        has_active_filters = True
    # Área só conta como filtro ativo se o usuário for admin
    if g.user.is_admin and selected_area_filter:
        has_active_filters = True

    return render_template(
        'projects_list.html', 
        projects=projects_paginated,
        page=page,
        total_pages=total_pages,
        total_projects=total_projects,
        search_query=search_query,
        selected_priority=selected_priority,
        selected_status=selected_status,
        selected_area=selected_area_filter, 
        selected_atraso=selected_atraso,
        selected_special_project=selected_special_project,
        selected_delivery_type=selected_delivery_type,
        selected_abep_indicator=selected_abep_indicator,
        selected_objetivo=selected_objetivo,
        areas=areas_options_for_dropdown,
        priorities=priorities_options,
        statuses=statuses_options,
        atrasos_options=atrasos_options,
        objetivos=objetivos,
        special_projects_options=special_projects_options,
        delivery_types_options=delivery_types_options,
        has_active_filters=has_active_filters,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES
    )

@main_bp.route('/projetos_pendentes')
@login_required
def list_projetos_pendentes():
    selected_area_filter = request.args.get('area')
    filtro_periodo = request.args.get('periodo', 'atrasados')  # Novo parâmetro com default 'atrasados'
    data_atual = datetime.date.today()
    projetos_pendentes_com_etapas = []

    query_projetos_base = Project.query.filter(Project.status == 'Vigente')

    # Filtro de área
    if g.user.is_admin:
        if selected_area_filter:
            query_projetos_base = query_projetos_base.filter(Project.area_responsavel == selected_area_filter)
    else: # Se não for admin, filtra pelas suas áreas
        user_areas = g.user.get_areas()
        if user_areas:
            query_projetos_base = query_projetos_base.filter(Project.area_responsavel.in_(user_areas))
        else: # Não-admin sem área não deve ver nenhum projeto
            query_projetos_base = query_projetos_base.filter(Project.id == -1) 

    projetos_vigentes = query_projetos_base.all()

    for projeto in projetos_vigentes:
        # Aplicar filtro de período nas etapas
        if filtro_periodo == 'atrasados':
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim < data_atual
            ).order_by(Etapa.data_fim).all()
        elif filtro_periodo == '7dias':
            # Inclui atrasados + próximos 7 dias
            data_limite = data_atual + datetime.timedelta(days=7)
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim <= data_limite
            ).order_by(Etapa.data_fim).all()
        elif filtro_periodo == '14dias':
            # Inclui atrasados + próximos 14 dias
            data_limite = data_atual + datetime.timedelta(days=14)
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim <= data_limite
            ).order_by(Etapa.data_fim).all()
        else:
            # Fallback para atrasados se o valor for inválido
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim < data_atual
            ).order_by(Etapa.data_fim).all()

        if etapas_filtradas:
            projetos_pendentes_com_etapas.append({
                'projeto': projeto,
                'etapas_atrasadas': etapas_filtradas  # Nome mantido por compatibilidade com o template
            })
    
    # Opções de área para o dropdown (apenas para admin)
    areas_options_for_dropdown = []
    if g.user.is_admin:
        project_areas_in_db = set(p.area_responsavel for p in Project.query.all() if p.area_responsavel)
        areas_options_for_dropdown = sorted(list(project_areas_in_db.union(set(AREAS_RESPONSAVEIS_CHOICES))))

    # Necessário para o formulário de criação de projeto
    # (objetivo -> resultado esperado -> indicadores)
    objetivos, _, _ = get_goal_catalog_context()

    return render_template(
        'projetos_pendentes.html',
        projetos_com_etapas=projetos_pendentes_com_etapas,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES,
        # Variáveis para os filtros
        areas_options=areas_options_for_dropdown,
        selected_area=selected_area_filter,
        filtro_periodo=filtro_periodo  # Novo parâmetro
    )

@main_bp.route('/add_project', methods=['POST'])
@login_required
def add_project():
    try:
        titulo = request.form.get('project_titulo')
        if not titulo:
            flash('O título do projeto é obrigatório.', 'danger')
            # Redirecionar para o painel pode ser uma boa opção de fallback
            return redirect(request.referrer or url_for('main.dashboard'))

        area_responsavel = request.form.get('project_area_responsavel')
        
        # Verificação de permissão: usuário pode criar projeto apenas em suas áreas
        if not g.user.is_admin:
            if not area_responsavel:
                flash('Você deve selecionar uma área para o projeto.', 'danger')
                return redirect(request.referrer or url_for('main.dashboard'))
            if not g.user.has_access_to_area(area_responsavel):
                flash('Você não tem permissão para criar projetos nesta área.', 'danger')
                return redirect(request.referrer or url_for('main.dashboard'))
        
        orgao = request.form.get('project_orgao')
        prioridade = request.form.get('project_prioridade')
        objetivo_id_raw = request.form.get('project_objetivo')
        resultado_esperado_id_raw = request.form.get('project_resultado')
        observacao = request.form.get('project_observacao')
        indicador_ids_raw = request.form.getlist('project_indicadores')

        objetivo_id, resultado_esperado_id, indicador_ids = normalize_goal_selection(
            objetivo_id_raw,
            resultado_esperado_id_raw,
            indicador_ids_raw,
        )
        
        # Novos campos
        special_project = request.form.get('project_special_project') or None
        sei_process = request.form.get('project_sei_process') or None
        short_description = request.form.get('project_short_description') or None
        delivery_type = request.form.get('project_delivery_type') or None
        abep_indicator = normalize_abep_indicator(request.form.get('project_abep_indicator'))
        github_link = request.form.get('project_github_link') or None
        documentation_link = request.form.get('project_documentation_link') or None
        
        # Etapas importadas do modelo
        etapa_descricoes = request.form.getlist('etapa_descricao')
        etapa_durations = request.form.getlist('etapa_duration')  # Durações em dias
        project_start_date = request.form.get('project_start_date')  # Data de início do projeto

        new_project = Project(
            titulo=titulo,
            area_responsavel=area_responsavel,
            orgao=orgao,
            prioridade=prioridade,
            objetivo_id=objetivo_id,
            resultado_esperado_id=resultado_esperado_id,
            observacao=observacao,
            status='Vigente',  # Definir status padrão
            special_project=special_project,
            sei_process=sei_process,
            short_description=short_description,
            delivery_type=delivery_type,
            abep_indicator=abep_indicator,
            github_link=github_link,
            documentation_link=documentation_link
        )
        db.session.add(new_project)
        db.session.flush()  # Para obter o new_project.id para as etapas e indicadores

        # Adicionar as etapas ao novo projeto com cálculo automático de datas
        current_date = None
        if project_start_date:
            try:
                from datetime import datetime, timedelta
                current_date = datetime.strptime(project_start_date, '%Y-%m-%d').date()
            except:
                current_date = None
        
        for i, descricao in enumerate(etapa_descricoes):
            if descricao.strip():  # Apenas adiciona se não estiver vazio
                data_inicio = None
                data_fim = None
                
                # Se há data de início e duração, calcular automaticamente
                if current_date and i < len(etapa_durations) and etapa_durations[i]:
                    try:
                        from datetime import timedelta
                        duration = int(etapa_durations[i])
                        data_inicio = current_date
                        data_fim = current_date + timedelta(days=duration - 1)  # -1 porque o início conta como dia 1
                        current_date = data_fim + timedelta(days=1)  # Próxima etapa começa no dia seguinte
                    except:
                        pass
                
                nova_etapa = Etapa(
                    descricao=descricao,
                    project_id=new_project.id,
                    ordem=i,
                    data_inicio=data_inicio,
                    data_fim=data_fim
                )
                db.session.add(nova_etapa)

        # Adicionar os indicadores
        if indicador_ids:
            for ind_id in indicador_ids:
                indicador_projeto = IndicadorProjeto(project_id=new_project.id, indicador_id=ind_id)
                db.session.add(indicador_projeto)

        # Registrar no histórico
        log_project_action(
            project_id=new_project.id,
            action_type='create',
            description=f'Criou o projeto "{titulo}"'
        )
        
        db.session.commit()
        
        flash('Projeto adicionado com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=new_project.id))

    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'warning')
        return redirect(request.referrer or url_for('main.dashboard'))
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao adicionar o projeto: {e}', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))


@main_bp.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para visualizar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    # O cálculo do índice de exibição dinâmico foi removido.
    # O ID real do projeto (project.id) será usado diretamente no template.
            
    return render_template('project_detail.html', project=project)


@main_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project_to_edit = Project.query.get_or_404(project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_edit.area_responsavel):
        flash('Você não tem permissão para editar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    objetivos, resultados_por_objetivo, indicadores_por_resultado = get_goal_catalog_context()

    indicadores_do_projeto_ids = [ip.indicador_id for ip in project_to_edit.indicadores]

    if request.method == 'POST':
        # Capturar valores anteriores para o histórico
        changes = []
        old_titulo = project_to_edit.titulo
        
        new_titulo = request.form.get('project_titulo')
        if old_titulo != new_titulo:
            changes.append(f'título de "{old_titulo}" para "{new_titulo}"')
        project_to_edit.titulo = new_titulo
        
        # Atualiza o órgão do projeto com o valor do formulário, independentemente do tipo de usuário.
        old_orgao = project_to_edit.orgao
        new_orgao = request.form.get('project_orgao')
        if old_orgao != new_orgao:
            changes.append(f'órgão de "{old_orgao or "vazio"}" para "{new_orgao or "vazio"}"')
        project_to_edit.orgao = new_orgao

        # Admin ou usuário com múltiplas áreas pode alterar área
        new_area = request.form.get('project_area_responsavel')
        if new_area:
            old_area = project_to_edit.area_responsavel
            user_areas = g.user.get_areas()
            if g.user.is_admin or (len(user_areas) > 1 and new_area in user_areas):
                if old_area != new_area:
                    changes.append(f'área responsável de "{old_area}" para "{new_area}"')
                project_to_edit.area_responsavel = new_area

        old_prioridade = project_to_edit.prioridade
        new_prioridade = request.form.get('project_prioridade')
        if old_prioridade != new_prioridade:
            changes.append(f'prioridade de "{old_prioridade}" para "{new_prioridade}"')
        project_to_edit.prioridade = new_prioridade
        
        old_status = project_to_edit.status
        new_status = request.form.get('project_status')
        if old_status != new_status:
            changes.append(f'status de "{old_status}" para "{new_status}"')
        project_to_edit.status = new_status
        
        project_to_edit.observacao = request.form.get('project_observacao')
        
        # Processar novos campos
        project_to_edit.special_project = request.form.get('project_special_project') or None
        project_to_edit.sei_process = request.form.get('project_sei_process') or None
        project_to_edit.short_description = request.form.get('project_short_description') or None
        project_to_edit.delivery_type = request.form.get('project_delivery_type') or None
        project_to_edit.github_link = request.form.get('project_github_link') or None
        project_to_edit.documentation_link = request.form.get('project_documentation_link') or None
        
        try:
            old_abep_indicator = project_to_edit.abep_indicator
            new_abep_indicator = normalize_abep_indicator(request.form.get('project_abep_indicator'))
            if old_abep_indicator != new_abep_indicator:
                changes.append(
                    f'indicador ABEP de "{old_abep_indicator or "vazio"}" para "{new_abep_indicator or "vazio"}"'
                )
            project_to_edit.abep_indicator = new_abep_indicator

            objetivo_id_norm, resultado_id_norm, indicadores_ids_norm = normalize_goal_selection(
                request.form.get('project_objetivo'),
                request.form.get('project_resultado'),
                request.form.getlist('project_indicadores'),
            )
        except ValueError as e:
            flash(str(e), 'warning')
            return redirect(url_for('main.edit_project', project_id=project_id))

        project_to_edit.objetivo_id = objetivo_id_norm
        project_to_edit.resultado_esperado_id = resultado_id_norm

        # Atualizar Indicadores
        IndicadorProjeto.query.filter_by(project_id=project_id).delete() # Remove todos os antigos
        for indicador_id in indicadores_ids_norm:
            indicador_projeto_novo = IndicadorProjeto(project_id=project_id, indicador_id=indicador_id)
            db.session.add(indicador_projeto_novo)
        
        # Registrar no histórico
        if changes:
            change_desc = ', '.join(changes)
            log_project_action(
                project_id=project_id,
                action_type='edit',
                description=f'Editou o projeto: alterou {change_desc}'
            )
        
        db.session.commit()
        flash(f'Projeto "{project_to_edit.titulo}" atualizado com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    return render_template(
        'project_form.html', 
        project=project_to_edit, 
        areas_responsaveis=AREAS_RESPONSAVEIS_CHOICES, # Lista de todas as áreas possíveis para o dropdown
        objetivos=objetivos,
        resultados_por_objetivo=resultados_por_objetivo,
        indicadores_por_resultado=indicadores_por_resultado,
        indicadores_do_projeto=indicadores_do_projeto_ids # Lista de IDs dos indicadores já associados
    )

@main_bp.route('/project/<int:project_id>/edit_data', methods=['GET'])
@login_required
def get_project_edit_data(project_id):
    """Endpoint AJAX para buscar dados necessários para edição"""
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para editar este projeto.'}), 403
    
    try:
        objetivos, resultados_por_objetivo, indicadores_por_resultado = get_goal_catalog_context()
        
        indicadores_do_projeto_ids = [ip.indicador_id for ip in project.indicadores]
        
        return jsonify({
            'success': True,
            'objetivos': objetivos,
            'resultados_por_objetivo': resultados_por_objetivo,
            'indicadores_por_resultado': indicadores_por_resultado,
            'indicadores_do_projeto': indicadores_do_projeto_ids,
            'areas_responsaveis': AREAS_RESPONSAVEIS_CHOICES,
            'is_admin': g.user.is_admin
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao buscar dados: {str(e)}'}), 500

@main_bp.route('/project/<int:project_id>/update_inline', methods=['POST'])
@login_required
def update_project_inline(project_id):
    """Endpoint AJAX para atualizar projeto inline"""
    project_to_edit = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_edit.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para editar este projeto.'}), 403
    
    try:
        data = request.get_json()
        changes = []
        
        # Atualizar campos básicos
        if 'titulo' in data and data['titulo'] != project_to_edit.titulo:
            changes.append(f'título de "{project_to_edit.titulo}" para "{data["titulo"]}"')
            project_to_edit.titulo = data['titulo']
        
        if 'status' in data and data['status'] != project_to_edit.status:
            changes.append(f'status de "{project_to_edit.status}" para "{data["status"]}"')
            project_to_edit.status = data['status']
        
        if 'prioridade' in data and data['prioridade'] != project_to_edit.prioridade:
            changes.append(f'prioridade de "{project_to_edit.prioridade}" para "{data["prioridade"]}"')
            project_to_edit.prioridade = data['prioridade']
        
        if 'orgao' in data:
            old_orgao = project_to_edit.orgao or ""
            new_orgao = data['orgao'] or ""
            if old_orgao != new_orgao:
                changes.append(f'órgão de "{old_orgao or "vazio"}" para "{new_orgao or "vazio"}"')
            project_to_edit.orgao = data['orgao'] or None
        
        # Admin ou usuário com múltiplas áreas pode alterar área
        if 'area_responsavel' in data:
            new_area = data['area_responsavel']
            if new_area != project_to_edit.area_responsavel:
                user_areas = g.user.get_areas()
                if g.user.is_admin or (len(user_areas) > 1 and new_area in user_areas):
                    changes.append(f'área de "{project_to_edit.area_responsavel}" para "{new_area}"')
                    project_to_edit.area_responsavel = new_area
        
        # Novos campos
        if 'special_project' in data:
            project_to_edit.special_project = data['special_project'] or None
        
        if 'sei_process' in data:
            project_to_edit.sei_process = data['sei_process'] or None
        
        if 'short_description' in data:
            project_to_edit.short_description = data['short_description'] or None
        
        if 'delivery_type' in data:
            project_to_edit.delivery_type = data['delivery_type'] or None

        if 'abep_indicator' in data:
            old_abep = project_to_edit.abep_indicator
            new_abep = normalize_abep_indicator(data['abep_indicator'])
            if old_abep != new_abep:
                changes.append(
                    f'indicador ABEP de "{old_abep or "vazio"}" para "{new_abep or "vazio"}"'
                )
            project_to_edit.abep_indicator = new_abep
        
        if 'github_link' in data:
            project_to_edit.github_link = data['github_link'] or None
        
        if 'documentation_link' in data:
            project_to_edit.documentation_link = data['documentation_link'] or None
        
        if 'observacao' in data:
            project_to_edit.observacao = data['observacao'] or None
        
        # Objetivo, Resultado e Indicadores
        goal_fields_present = any(
            field in data for field in ('objetivo_id', 'resultado_esperado_id', 'indicadores_ids')
        )
        if goal_fields_present:
            objetivo_raw = data.get('objetivo_id', project_to_edit.objetivo_id)
            resultado_raw = data.get('resultado_esperado_id', project_to_edit.resultado_esperado_id)
            indicadores_raw = data.get(
                'indicadores_ids',
                [ip.indicador_id for ip in project_to_edit.indicadores],
            )

            objetivo_norm, resultado_norm, indicadores_norm = normalize_goal_selection(
                objetivo_raw,
                resultado_raw,
                indicadores_raw,
            )

            project_to_edit.objetivo_id = objetivo_norm
            project_to_edit.resultado_esperado_id = resultado_norm

            # Atualizar indicadores
            IndicadorProjeto.query.filter_by(project_id=project_id).delete()
            for indicador_id in indicadores_norm:
                indicador_projeto_novo = IndicadorProjeto(
                    project_id=project_id,
                    indicador_id=indicador_id,
                )
                db.session.add(indicador_projeto_novo)
        
        # Registrar no histórico
        if changes:
            change_desc = ', '.join(changes)
            log_project_action(
                project_id=project_id,
                action_type='edit',
                description=f'Editou o projeto (inline): alterou {change_desc}'
            )
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Projeto atualizado com sucesso!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao atualizar projeto: {str(e)}'}), 500

@main_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
# @admin_required # Decida se apenas admin pode excluir. Se não, a lógica abaixo se aplica.
def delete_project(project_id):
    project_to_delete = Project.query.get_or_404(project_id)

    # Permissão para excluir: Admin pode excluir qualquer um.
    # Usuário não-admin só pode excluir projetos de suas áreas.
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_delete.area_responsavel):
        flash('Você não tem permissão para excluir este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))
    
    # Registrar no histórico antes de excluir
    project_titulo = project_to_delete.titulo
    log_project_action(
        project_id=project_to_delete.id,
        action_type='delete',
        description=f'Excluiu o projeto "{project_titulo}"'
    )
    
    db.session.delete(project_to_delete)
    db.session.commit()
    flash(f'Projeto "{project_titulo}" e suas etapas foram excluídos.', 'success')
    return redirect(url_for('main.list_projects'))

@main_bp.route('/project/<int:project_id>/concluir', methods=['POST'])
@login_required
def concluir_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para concluir este projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Verificar se o projeto está Vigente
    if project.status != 'Vigente':
        flash('Apenas projetos com status "Vigente" podem ser concluídos.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Verificar se todas as etapas estão concluídas
    if not project.todas_etapas_concluidas:
        flash('Todas as etapas devem estar iniciadas e concluídas para finalizar o projeto.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Atualizar status
    project.status = 'Finalizado'
    
    # Registrar no histórico
    log_project_action(
        project_id=project.id,
        action_type='finalize',
        description=f'Concluiu o projeto "{project.titulo}"'
    )
    
    db.session.commit()
    flash(f'Projeto "{project.titulo}" foi concluído com sucesso!', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id))

# --- Rotas de Etapa (com verificação de permissão no projeto pai) ---
@main_bp.route('/project/<int:project_id>/etapa/add', methods=['POST'])
@login_required
def add_etapa(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para adicionar etapas a este projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id)) # Ou para list_projects

    descricao = request.form.get('etapa_descricao')
    if not descricao:
        flash('A descrição da etapa é obrigatória.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    data_inicio_str = request.form.get('etapa_data_inicio')
    data_fim_str = request.form.get('etapa_data_fim')
    responsavel = request.form.get('etapa_responsavel')
    comentarios = request.form.get('etapa_comentarios')
    etapa_iniciada = request.form.get('etapa_iniciada') == 'on'
    etapa_concluida = request.form.get('etapa_done') == 'on'

    if not etapa_iniciada and etapa_concluida:
        flash('Uma etapa não pode ser marcada como concluída sem ser iniciada.', 'warning')
        etapa_concluida = False # Força para não concluída

    data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
    data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

    # Calcular a ordem da nova etapa
    ultima_etapa = Etapa.query.with_parent(project).order_by(Etapa.ordem.desc()).first()
    nova_ordem = (ultima_etapa.ordem + 1) if ultima_etapa else 0

    new_etapa = Etapa(
        descricao=descricao, data_inicio=data_inicio, data_fim=data_fim,
        responsavel=responsavel, iniciada=etapa_iniciada, done=etapa_concluida,
        comentarios=comentarios, project_id=project.id, ordem=nova_ordem  # Adicionado ordem
    )
    db.session.add(new_etapa)
    
    # Registrar no histórico
    log_project_action(
        project_id=project.id,
        action_type='add_etapa',
        description=f'Adicionou a etapa "{descricao}"'
    )
    
    db.session.commit()
    flash('Etapa adicionada com sucesso!', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id))

@main_bp.route('/project/<int:project_id>/import_model', methods=['POST'])
@login_required
def import_model_to_project(project_id):
    """Importa etapas de um modelo para um projeto existente"""
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para importar modelos neste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    template_id = request.form.get('template_id')
    start_date_str = request.form.get('start_date')
    
    if not template_id or not start_date_str:
        flash('Selecione um modelo e defina a data de início.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Buscar o modelo
    template = StageTemplate.query.get_or_404(template_id)
    
    if not template.items:
        flash('Este modelo não possui etapas.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    try:
        from datetime import datetime, timedelta
        
        # Converter data de início
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        current_date = start_date
        
        # Calcular a próxima ordem disponível
        ultima_etapa = Etapa.query.with_parent(project).order_by(Etapa.ordem.desc()).first()
        ordem_inicial = (ultima_etapa.ordem + 1) if ultima_etapa else 0
        
        # Criar etapas baseadas no modelo
        etapas_criadas = 0
        for index, item in enumerate(template.items):
            # Calcular datas
            data_inicio = current_date
            data_fim = current_date + timedelta(days=item.duration_days - 1)
            
            # Criar etapa
            nova_etapa = Etapa(
                descricao=item.name,
                data_inicio=data_inicio,
                data_fim=data_fim,
                project_id=project.id,
                ordem=ordem_inicial + index,
                iniciada=False,
                done=False
            )
            db.session.add(nova_etapa)
            etapas_criadas += 1
            
            # Próxima etapa começa no dia seguinte ao fim desta
            current_date = data_fim + timedelta(days=1)
        
        # Registrar no histórico
        log_project_action(
            project_id=project.id,
            action_type='import_model',
            description=f'Importou {etapas_criadas} etapa(s) do modelo "{template.name}"'
        )
        
        db.session.commit()
        flash(f'{etapas_criadas} etapa(s) importada(s) com sucesso do modelo "{template.name}"!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao importar modelo: {str(e)}', 'danger')
    
    return redirect(url_for('main.project_detail', project_id=project_id))

@main_bp.route('/etapa/<int:etapa_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_etapa(etapa_id):
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project # Projeto pai da etapa
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        flash('Você não tem permissão para editar etapas deste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_of_etapa.id))

    if request.method == 'POST':
        old_descricao = etapa.descricao
        etapa.descricao = request.form.get('etapa_descricao')
        etapa.responsavel = request.form.get('etapa_responsavel')
        etapa.comentarios = request.form.get('etapa_comentarios')
        etapa.iniciada = request.form.get('etapa_iniciada') == 'on'
        etapa_done_form = request.form.get('etapa_done') == 'on'

        if not etapa.iniciada and etapa_done_form:
            flash('A etapa não pode ser marcada como concluída pois não foi iniciada.', 'warning')
            etapa.done = False
        else:
            etapa.done = etapa_done_form
            
        data_inicio_str = request.form.get('etapa_data_inicio')
        etapa.data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim_str = request.form.get('etapa_data_fim')
        etapa.data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
        
        # Registrar no histórico
        log_project_action(
            project_id=etapa.project_id,
            action_type='edit_etapa',
            description=f'Editou a etapa "{old_descricao}"'
        )
        
        db.session.commit()
        flash('Etapa atualizada com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=etapa.project_id))

    data_inicio_f = etapa.data_inicio.strftime('%Y-%m-%d') if etapa.data_inicio else ''
    data_fim_f = etapa.data_fim.strftime('%Y-%m-%d') if etapa.data_fim else ''
    return render_template('etapa_form.html', etapa=etapa, action=url_for('main.edit_etapa', etapa_id=etapa_id), data_inicio_form=data_inicio_f, data_fim_form=data_fim_f)

@main_bp.route('/etapa/<int:etapa_id>/delete', methods=['POST'])
@login_required
def delete_etapa(etapa_id):
    etapa_to_delete = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa_to_delete.project
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        flash('Você não tem permissão para excluir etapas deste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_of_etapa.id))

    project_id_for_redirect = etapa_to_delete.project_id
    etapa_descricao = etapa_to_delete.descricao
    
    # Registrar no histórico
    log_project_action(
        project_id=project_id_for_redirect,
        action_type='delete_etapa',
        description=f'Excluiu a etapa "{etapa_descricao}"'
    )
    
    db.session.delete(etapa_to_delete)
    db.session.commit()
    flash('Etapa excluída com sucesso.', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

@main_bp.route('/project/<int:project_id>/etapas/reordenar', methods=['POST'])
@login_required
def reorder_etapas(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para reordenar etapas deste projeto.'}), 403

    data = request.get_json()
    etapa_ids_ordenadas = data.get('etapa_ids')

    if not etapa_ids_ordenadas or not isinstance(etapa_ids_ordenadas, list):
        return jsonify({'success': False, 'message': 'Lista de IDs de etapas inválida.'}), 400

    try:
        for index, etapa_id in enumerate(etapa_ids_ordenadas):
            etapa = Etapa.query.filter_by(id=etapa_id, project_id=project.id).first()
            if etapa:
                etapa.ordem = index
            else:
                # Tratar caso onde um ID de etapa não pertence ao projeto ou não existe
                # Pode ser um erro, ou apenas ignorar silenciosamente dependendo da política
                # Por segurança, vamos logar e retornar um erro se um ID for inválido.
                print(f"Tentativa de reordenar etapa inválida (ID: {etapa_id}) para o projeto {project.id}")
                # Poderia lançar uma exceção ou retornar um erro específico
        
        db.session.commit()
        # flash('Ordem das etapas atualizada com sucesso!', 'success') # Flash não funciona bem com AJAX
        return jsonify({'success': True, 'message': 'Ordem das etapas atualizada.'})
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao reordenar etapas: {e}")
        return jsonify({'success': False, 'message': 'Erro ao atualizar a ordem das etapas.'}), 500

@main_bp.route('/etapa/<int:etapa_id>/toggle_iniciada', methods=['POST'])
@login_required
def toggle_iniciada_etapa(etapa_id):
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403

    etapa.iniciada = not etapa.iniciada
    ajax_flash_message = None
    
    # Registrar no histórico
    status_text = 'iniciada' if etapa.iniciada else 'não iniciada'
    log_project_action(
        project_id=etapa.project_id,
        action_type='toggle_iniciada',
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}'
    )
    
    if not etapa.iniciada and etapa.done: # Se desmarcou iniciada e estava concluída
        etapa.done = False
        ajax_flash_message = 'Etapa marcada como não iniciada e, consequentemente, como não concluída.'
    db.session.commit()
    return jsonify({
        'success': True, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada, 
        'done': etapa.done, 'message': ajax_flash_message
    })

@main_bp.route('/etapa/<int:etapa_id>/toggle', methods=['POST']) # Rota para toggle 'done'
@login_required
def toggle_etapa(etapa_id): # Renomeada para evitar conflito, mas a URL é a mesma
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403

    if not etapa.iniciada and not etapa.done: # Tentando marcar como 'done' sem estar 'iniciada'
        return jsonify({
            'success': False, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada,
            'done': etapa.done, 'message': 'Não é possível concluir uma etapa que não foi iniciada.'
        })
    
    etapa.done = not etapa.done
    
    # Registrar no histórico
    status_text = 'concluída' if etapa.done else 'não concluída'
    log_project_action(
        project_id=etapa.project_id,
        action_type='toggle_done',
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}'
    )
    
    db.session.commit()
    return jsonify({
        'success': True, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada, 
        'done': etapa.done, 'message': None # Nenhuma mensagem específica aqui a menos que haja um caso
    })

@main_bp.route('/etapa/<int:etapa_id>/update_field', methods=['POST'])
@login_required
def update_etapa_field(etapa_id):
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project
    
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    field = data.get('field')
    value = data.get('value')

    if field not in ['descricao', 'data_inicio', 'data_fim', 'responsavel']:
        return jsonify({'success': False, 'message': 'Campo inválido.'}), 400

    try:
        response_data = {'success': True}
        
        # Mapeamento de nomes de campos para exibição
        field_names = {
            'descricao': 'descrição',
            'data_inicio': 'data de início',
            'data_fim': 'data de fim',
            'responsavel': 'responsável'
        }
        field_display = field_names.get(field, field)
        
        if field == 'data_inicio':
            old_date = etapa.data_inicio
            new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            
            # Registrar no histórico
            old_value_str = old_date.strftime('%d/%m/%Y') if old_date else 'vazio'
            new_value_str = new_date.strftime('%d/%m/%Y') if new_date else 'vazio'
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa "{etapa.descricao}"',
                old_value=old_value_str,
                new_value=new_value_str
            )
            
            etapa.data_inicio = new_date
            response_data['newValue'] = value
            response_data['displayValue'] = new_date.strftime('%d/%m/%Y') if new_date else '-'

            if old_date and new_date:
                delta = new_date - old_date
                if etapa.data_fim:
                    etapa.data_fim += delta
                    response_data['updatedEndDate'] = etapa.data_fim.strftime('%Y-%m-%d')
                    response_data['updatedEndDateDisplay'] = etapa.data_fim.strftime('%d/%m/%Y')
                response_data['daysDiff'] = delta.days
            
        elif field == 'data_fim':
            old_date = etapa.data_fim
            new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            
            # Registrar no histórico
            old_value_str = old_date.strftime('%d/%m/%Y') if old_date else 'vazio'
            new_value_str = new_date.strftime('%d/%m/%Y') if new_date else 'vazio'
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa "{etapa.descricao}"',
                old_value=old_value_str,
                new_value=new_value_str
            )
            
            etapa.data_fim = new_date
            response_data['newValue'] = value
            response_data['displayValue'] = new_date.strftime('%d/%m/%Y') if new_date else '-'
            
        elif field == 'descricao':
            old_value = etapa.descricao
            new_value = value
            
            # Registrar no histórico
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa',
                old_value=old_value or 'vazio',
                new_value=new_value or 'vazio'
            )
            
            etapa.descricao = new_value
            response_data['newValue'] = new_value
            response_data['displayValue'] = new_value if new_value else '-'
            
        elif field == 'responsavel':
            old_value = etapa.responsavel
            new_value = value
            
            # Registrar no histórico
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa "{etapa.descricao}"',
                old_value=old_value or 'vazio',
                new_value=new_value or 'vazio'
            )
            
            etapa.responsavel = new_value
            response_data['newValue'] = new_value
            response_data['displayValue'] = new_value if new_value else '-'
        
        db.session.commit()
        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao salvar a alteração.'}), 500

@main_bp.route('/etapa/<int:etapa_id>/comentario', methods=['POST'])
@login_required
def update_etapa_comentario(etapa_id):
    """Endpoint para adicionar/editar/remover comentário de uma etapa via modal."""
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project
    
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    comentario = data.get('comentario', '').strip()
    
    try:
        old_comentario = etapa.comentarios or 'vazio'
        new_comentario = comentario if comentario else 'vazio'
        
        # Atualizar o comentário
        etapa.comentarios = comentario if comentario else None
        
        # Registrar no histórico
        action_description = 'Adicionou comentário' if comentario and old_comentario == 'vazio' else \
                             'Removeu comentário' if not comentario and old_comentario != 'vazio' else \
                             'Editou comentário'
        
        log_project_action(
            project_id=etapa.project_id,
            action_type='edit_etapa_comentario',
            description=f'{action_description} da etapa "{etapa.descricao}"',
            old_value=old_comentario,
            new_value=new_comentario
        )
        
        db.session.commit()
        
        message = 'Comentário salvo com sucesso!' if comentario else 'Comentário removido com sucesso!'
        return jsonify({'success': True, 'message': message})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao salvar comentário.'}), 500

@main_bp.route('/project/<int:project_id>/cascade_update', methods=['POST'])
@login_required
def cascade_date_update(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    base_etapa_id = data.get('etapa_id')
    days_to_add = data.get('days_diff')

    if not all([base_etapa_id, days_to_add is not None]):
         return jsonify({'success': False, 'message': 'Parâmetros inválidos.'}), 400

    try:
        days_delta = datetime.timedelta(days=days_to_add)
        base_etapa = Etapa.query.get(base_etapa_id)
        if not base_etapa or base_etapa.project_id != project_id:
            return jsonify({'success': False, 'message': 'Etapa base não encontrada.'}), 404
        
        subsequent_etapas = Etapa.query.filter(
            Etapa.project_id == project_id,
            Etapa.ordem > base_etapa.ordem
        ).all()

        for etapa in subsequent_etapas:
            if etapa.data_inicio:
                etapa.data_inicio += days_delta
            if etapa.data_fim:
                etapa.data_fim += days_delta
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Datas subsequentes atualizadas com sucesso.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao atualizar datas subsequentes.'}), 500


# --- Rotas de Gerenciamento de Usuários (Admin) ---
@main_bp.route('/admin/users')
@login_required
@admin_required
def list_users():
    page = request.args.get('page', 1, type=int)
    # Ordenar por nome ou ID, por exemplo
    users_pagination = User.query.order_by(User.name).paginate(page=page, per_page=10)
    return render_template('list_users.html', users=users_pagination)

@main_bp.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        name = request.form.get('name')
        password = request.form.get('password')
        orgao = request.form.get('orgao')
        areas_responsavel_form = request.form.getlist('areas_responsavel') # Lista de áreas
        is_admin_form = request.form.get('is_admin') == 'on'

        if not username or not name or not password:
            flash('Username, Nome Completo e Senha são obrigatórios.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Este nome de usuário já está em uso. Escolha outro.', 'danger')
        else:
            new_user = User(
                username=username, 
                name=name, 
                orgao=orgao if orgao else None, 
                is_admin=is_admin_form
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()  # Para obter o ID do usuário
            
            # Adicionar áreas selecionadas
            for area in areas_responsavel_form:
                if area:  # Ignora strings vazias
                    user_area = UserArea(user_id=new_user.id, area=area)
                    db.session.add(user_area)
            
            db.session.commit()
            flash(f'Usuário "{name}" ({username}) criado com sucesso!', 'success')
            return redirect(url_for('main.list_users'))
        # Se caiu aqui, houve erro, então renderiza o form novamente com os dados (se o template suportar)
        # ou apenas renderiza o form vazio.
        return render_template('user_form.html', user=request.form, user_areas=areas_responsavel_form, action_verb="Adicionar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)


    # Método GET: exibe o formulário para adicionar novo usuário
    return render_template('user_form.html', user=User(), user_areas=[], action_verb="Adicionar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)


@main_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        # Username geralmente não é editável ou requer cuidados especiais de unicidade
        user_to_edit.name = request.form.get('name')
        user_to_edit.orgao = request.form.get('orgao') if request.form.get('orgao') else None
        areas_responsavel_form = request.form.getlist('areas_responsavel') # Lista de áreas
        
        is_admin_form_val = request.form.get('is_admin') == 'on'

        # Lógica para impedir que o último admin se despromova
        if user_to_edit.is_admin and not is_admin_form_val: # Tentando remover status de admin
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                flash('Não é possível remover o status de administrador do único administrador existente.', 'danger')
                # Não altera user_to_edit.is_admin e recarrega o form
                return render_template('user_form.html', user=user_to_edit, user_areas=user_to_edit.get_areas(), action_verb="Editar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)
        
        user_to_edit.is_admin = is_admin_form_val

        # Atualizar áreas do usuário
        user_to_edit.set_areas(areas_responsavel_form)

        new_password = request.form.get('password')
        if new_password: # Só atualiza a senha se uma nova for fornecida
            user_to_edit.set_password(new_password)
            
        db.session.commit()
        flash(f'Usuário "{user_to_edit.name}" atualizado com sucesso!', 'success')
        return redirect(url_for('main.list_users'))
    
    # Método GET
    return render_template('user_form.html', user=user_to_edit, user_areas=user_to_edit.get_areas(), action_verb="Editar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)

@main_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)

    if user_to_delete.id == g.user.id: # Admin não pode se auto-excluir
        flash('Você não pode excluir sua própria conta de administrador.', 'danger')
        return redirect(url_for('main.list_users'))

    if user_to_delete.is_admin and User.query.filter_by(is_admin=True).count() == 1:
        flash('Não é possível excluir o único administrador do sistema.', 'danger')
        return redirect(url_for('main.list_users'))
    
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'Usuário {user_to_delete.username} excluído com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir o usuário: {str(e)}', 'danger')

    return redirect(url_for('main.list_users'))


# --- Rotas para Modelos de Etapas (Admin) ---

@main_bp.route('/admin/templates')
@login_required
@admin_required
def list_templates():
    # Usar joinedload para carregar os 'items' de forma eficiente (Eager Loading)
    # Isso garante que template.items esteja populado sem a necessidade de queries adicionais.
    templates = StageTemplate.query.options(joinedload(StageTemplate.items)).order_by(StageTemplate.name).all()
    return render_template('template_list.html', templates=templates)

@main_bp.route('/admin/templates/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_template():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        stage_names = request.form.getlist('stage_name')
        stage_durations = request.form.getlist('stage_duration')

        if not name or not stage_names:
            flash('O nome do modelo e pelo menos uma etapa são obrigatórios.', 'danger')
            return render_template('template_form.html')

        new_template = StageTemplate(name=name, description=description)
        db.session.add(new_template)
        # Flush para obter o ID do novo template antes de criar os itens
        db.session.flush()

        for i, stage_name in enumerate(stage_names):
            if stage_name: # Ignorar campos de etapa vazios
                duration = int(stage_durations[i]) if i < len(stage_durations) and stage_durations[i] else 1
                item = StageTemplateItem(
                    name=stage_name,
                    duration_days=duration,
                    order=i,
                    templateId=new_template.id
                )
                db.session.add(item)
        
        db.session.commit()
        flash('Modelo de etapas criado com sucesso!', 'success')
        return redirect(url_for('main.list_templates'))

    return render_template('template_form.html')

@main_bp.route('/admin/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_template(template_id):
    template = StageTemplate.query.get_or_404(template_id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        stage_names = request.form.getlist('stage_name')
        stage_durations = request.form.getlist('stage_duration')

        if not name or not stage_names:
            flash('O nome do modelo e pelo menos uma etapa são obrigatórios.', 'danger')
            return render_template('template_form.html', template=template)

        # Atualiza os dados do template
        template.name = name
        template.description = description

        # Remove os itens antigos
        StageTemplateItem.query.filter_by(templateId=template.id).delete()

        # Adiciona os novos itens
        for i, stage_name in enumerate(stage_names):
            if stage_name:
                duration = int(stage_durations[i]) if i < len(stage_durations) and stage_durations[i] else 1
                item = StageTemplateItem(
                    name=stage_name,
                    duration_days=duration,
                    order=i,
                    templateId=template.id
                )
                db.session.add(item)
        
        db.session.commit()
        flash('Modelo de etapas atualizado com sucesso!', 'success')
        return redirect(url_for('main.list_templates'))

    return render_template('template_form.html', template=template)

@main_bp.route('/admin/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_template(template_id):
    template = StageTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    flash('Modelo de etapas excluído com sucesso.', 'success')
    return redirect(url_for('main.list_templates'))


# --- API Endpoints ---

@main_bp.route('/api/resultados/<int:objetivo_id>')
@login_required
def get_resultados(objetivo_id):
    if objetivo_id not in OBJETIVO_IDS:
        return jsonify({"error": "Objetivo não encontrado"}), 404

    return jsonify(get_resultados_for_objetivo(objetivo_id))

@main_bp.route('/api/indicadores/<int:resultado_id>')
@login_required
def get_indicadores(resultado_id):
    if resultado_id not in RESULTADO_IDS:
        return jsonify({"error": "Resultado esperado não encontrado"}), 404

    return jsonify(get_indicadores_for_resultado(resultado_id))

# --- API para Modelos de Etapas ---

@main_bp.route('/api/templates')
@login_required
def get_templates():
    templates = StageTemplate.query.order_by(StageTemplate.name).all()
    return jsonify([{'id': t.id, 'name': t.name} for t in templates])

@main_bp.route('/api/templates/<int:template_id>')
@login_required
def get_template_stages(template_id):
    template = StageTemplate.query.get_or_404(template_id)
    stages = [{'name': item.name, 'order': item.order, 'duration': item.duration_days} for item in template.items]
    return jsonify(stages)

@main_bp.route('/project/<int:project_id>/history')
@login_required
def project_history(project_id):
    """Visualizar histórico de ações de um projeto"""
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para visualizar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))
    
    # Buscar histórico ordenado por data (mais recente primeiro)
    history_entries = ProjectHistory.query.filter_by(project_id=project_id)\
        .order_by(ProjectHistory.timestamp.desc())\
        .all()
    
    return render_template('project_history.html', project=project, history=history_entries)

@main_bp.route('/setup_db')
# @login_required # Opcional: proteger esta rota
# @admin_required # Opcional: proteger esta rota
def setup_db():
    # Lembre-se que a tabela 'user' foi criada manualmente.
    # db.create_all() aqui NÃO vai recriar 'user' se ela já existir.
    # Só criaria outras tabelas dos modelos que ainda não existem.
    from flask import current_app # Importar aqui para evitar import circular no topo se routes for grande
    try:
        from sqlalchemy import inspect # Importar aqui
        inspector = inspect(db.engine)
        
        tabelas_existentes = inspector.get_table_names()
        tabela_project_existe = 'project' in tabelas_existentes
        tabela_user_existe = 'user' in tabelas_existentes
        force_creation = request.args.get('force', 'false').lower() == 'true'
        
        resultado = {
            "status": "success", "mensagem": "",
            "detalhes": {
                "tabelas_existentes": tabelas_existentes,
                "tabela_project_existe": tabela_project_existe,
                "tabela_user_existe": tabela_user_existe,
                "banco_de_dados": current_app.config['SQLALCHEMY_DATABASE_URI'],
                "ambiente": "Google App Engine" if os.getenv('GAE_ENV', '').startswith('standard') else "Desenvolvimento Local"
            }
        }
        
        # Se forçar ou se alguma das tabelas principais (project, user) não existir
        if force_creation or not tabela_project_existe or not tabela_user_existe:
            # CUIDADO: db.drop_all() APAGA TODOS OS DADOS. NÃO use em produção sem backup.
            # if force_creation:
            #     # db.drop_all() # Comentado por segurança
            #     resultado["mensagem"] += " (DROP ALL FOI COMENTADO POR SEGURANÇA) "
            
            db.create_all() # Cria tabelas FALTANTES. Não recria as existentes.
            resultado["mensagem"] += "Banco de dados configurado. Tabelas faltantes (re)criadas."
            resultado["detalhes"]["tabelas_criadas"] = True
        else:
            resultado["mensagem"] = "As tabelas principais já existem. Use ?force=true para tentar recriar tabelas faltantes (sem apagar dados existentes)."
            resultado["detalhes"]["tabelas_criadas"] = False

        sync_summary = sync_goal_catalog_to_db(commit=True)
        resultado["detalhes"]["catalogo_objetivos_sync"] = sync_summary

        # Garantir coluna de Indicador ABEP em bancos existentes
        inspector = inspect(db.engine)  # Recria para evitar cache de metadata antiga
        table_names_after = inspector.get_table_names()
        project_columns = {col["name"] for col in inspector.get_columns('project')} if 'project' in table_names_after else set()
        if 'project' in table_names_after and 'abep_indicator' not in project_columns:
            db.session.execute(text("ALTER TABLE project ADD COLUMN abep_indicator VARCHAR(255)"))
            db.session.commit()
            resultado["detalhes"]["abep_indicator_column"] = "created"
        else:
            resultado["detalhes"]["abep_indicator_column"] = "exists"
        
        accept_header = request.headers.get('Accept', '')
        if 'application/json' in accept_header:
            return jsonify(resultado)
        
        html_response = f"""
        <h1>Status do Banco de Dados</h1>
        <p><strong>Status:</strong> {resultado['status']}</p>
        <p><strong>Mensagem:</strong> {resultado['mensagem']}</p>
        <h2>Detalhes</h2><ul>
            <li><strong>Ambiente:</strong> {resultado['detalhes']['ambiente']}</li>
            <li><strong>Banco de Dados:</strong> {resultado['detalhes']['banco_de_dados']}</li>
            <li><strong>Tabela 'project' Existe:</strong> {resultado['detalhes']['tabela_project_existe']}</li>
            <li><strong>Tabela 'user' Existe:</strong> {resultado['detalhes']['tabela_user_existe']}</li>
            <li><strong>Tabelas Existentes:</strong> {', '.join(resultado['detalhes']['tabelas_existentes'])}</li>
            <li><strong>Sync Catálogo Objetivos:</strong> {resultado['detalhes'].get('catalogo_objetivos_sync', {})}</li>
        </ul>
        <p><a href="{url_for('main.home')}">Voltar</a> | <a href="{url_for('main.setup_db', force='true')}">Forçar criação de tabelas faltantes</a></p>
        """
        return html_response
            
    except Exception as e:
        error_msg = f"Erro ao configurar banco de dados: {str(e)}"
        current_app.logger.error(f"Erro em /setup_db: {error_msg}", exc_info=True)
        return jsonify({"status": "error", "mensagem": error_msg}) if 'application/json' in request.headers.get('Accept', '') else error_msg


# ===================================
# ROTAS DE TAREFAS (TASKS)
# ===================================

@main_bp.route('/tarefas', methods=['GET'])
@login_required
def list_tasks():
    """Lista tarefas do usuário com filtros e paginação"""
    # Filtros
    project_filter = request.args.get('project', '')
    search_query = request.args.get('search', '')
    
    # Query base
    query = Task.query.options(joinedload(Task.items), joinedload(Task.project))
    
    # Aplicar permissões
    if not g.user.is_admin:
        # Usuário vê: tarefas de projetos de suas áreas + tarefas sem projeto criadas por ele
        user_areas = g.user.get_areas()
        query = query.outerjoin(Project).filter(
            db.or_(
                db.and_(Task.project_id.isnot(None), Project.area_responsavel.in_(user_areas)),
                db.and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)
            )
        )
    
    # Aplicar filtros
    if project_filter:
        if project_filter == 'sem_projeto':
            query = query.filter(Task.project_id.is_(None))
        else:
            query = query.filter(Task.project_id == project_filter)
    
    if search_query:
        query = query.filter(Task.titulo.ilike(f'%{search_query}%'))
    
    # Ordenar por data de criação (mais recentes primeiro)
    query = query.order_by(Task.created_at.desc())
    
    # Paginação
    page = request.args.get('page', 1, type=int)
    per_page = 40
    tasks_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    tasks = tasks_pagination.items
    
    # Obter lista de projetos do usuário para o filtro
    if g.user.is_admin:
        projects_for_filter = Project.query.order_by(Project.titulo).all()
    else:
        user_areas = g.user.get_areas()
        projects_for_filter = Project.query.filter(Project.area_responsavel.in_(user_areas)).order_by(Project.titulo).all()
    
    return render_template('task_list.html', 
                         tasks=tasks,
                         pagination=tasks_pagination,
                         projects=projects_for_filter,
                         project_filter=project_filter,
                         search_query=search_query)


@main_bp.route('/tarefas/add', methods=['POST'])
@login_required
def add_task():
    """Adiciona nova tarefa"""
    titulo = request.form.get('titulo', '').strip()
    project_id = request.form.get('project_id', '').strip()
    
    # Validações
    if not titulo:
        flash('Título é obrigatório.', 'danger')
        return redirect(url_for('main.list_tasks'))
    
    # Validar project_id se fornecido
    project = None
    if project_id:
        try:
            project_id = int(project_id)
            project = Project.query.get(project_id)
            if not project:
                flash('Projeto não encontrado.', 'danger')
                return redirect(url_for('main.list_tasks'))
            
            # Verificar permissão de acesso ao projeto
            if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
                flash('Você não tem permissão para associar tarefas a este projeto.', 'danger')
                return redirect(url_for('main.list_tasks'))
        except (ValueError, TypeError):
            project_id = None
    else:
        project_id = None
    
    # Criar tarefa
    task = Task(
        titulo=titulo,
        project_id=project_id,
        created_by_id=g.user.id
    )
    
    try:
        db.session.add(task)
        db.session.commit()
        flash('Tarefa criada com sucesso!', 'success')
        # Redirecionar para a página de detalhes da tarefa
        return redirect(url_for('main.task_detail', task_id=task.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao criar tarefa: {str(e)}', 'danger')
    
    return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas/<int:task_id>', methods=['GET'])
@login_required
def task_detail(task_id):
    """Detalhes da tarefa com seus itens e comentários"""
    task = Task.query.options(
        joinedload(Task.items).joinedload(TaskItem.comments).joinedload(TaskItemComment.author),
        joinedload(Task.project)
    ).get_or_404(task_id)
    
    # Verificar permissão
    can_view = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_view:
        flash('Você não tem permissão para acessar esta tarefa.', 'danger')
        return redirect(url_for('main.list_tasks'))
    
    # Projetos para dropdown de edição (mesma regra de list_tasks)
    if g.user.is_admin:
        projects = Project.query.order_by(Project.titulo).all()
    else:
        user_areas = g.user.get_areas()
        projects = Project.query.filter(Project.area_responsavel.in_(user_areas)).order_by(Project.titulo).all()
    
    return render_template('task_detail.html', task=task, projects=projects)


@main_bp.route('/tarefas/<int:task_id>/edit', methods=['POST'])
@login_required
def edit_task(task_id):
    """Edita tarefa existente (título e projeto)"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    titulo = request.form.get('titulo', '').strip()
    project_id = request.form.get('project_id', '').strip()
    
    # Validações
    if not titulo:
        return jsonify({'success': False, 'message': 'Título é obrigatório'}), 400
    
    # Validar project_id se fornecido
    if project_id:
        try:
            project_id = int(project_id)
            project = Project.query.get(project_id)
            if not project:
                return jsonify({'success': False, 'message': 'Projeto não encontrado'}), 404
            
            # Verificar permissão de acesso ao projeto
            if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
                return jsonify({'success': False, 'message': 'Sem permissão para este projeto'}), 403
        except (ValueError, TypeError):
            project_id = None
    else:
        project_id = None
    
    # Atualizar tarefa
    task.titulo = titulo
    task.project_id = project_id
    
    try:
        db.session.commit()
        project_titulo = task.project.titulo if task.project else None
        return jsonify({
            'success': True,
            'message': 'Tarefa atualizada',
            'task': {
                'titulo': task.titulo,
                'project_id': task.project_id,
                'project_titulo': project_titulo
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """Exclui tarefa"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar permissão
    can_delete = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_delete:
        flash('Você não tem permissão para excluir esta tarefa.', 'danger')
        return redirect(url_for('main.list_tasks'))
    
    try:
        db.session.delete(task)
        db.session.commit()
        flash('Tarefa excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir tarefa: {str(e)}', 'danger')
    
    return redirect(url_for('main.list_tasks'))


# ===================================
# ROTAS DE ITENS DE TAREFA (TASK ITEMS)
# ===================================

@main_bp.route('/tarefas/<int:task_id>/itens/add', methods=['POST'])
@login_required
def add_task_item(task_id):
    """Adiciona item à tarefa"""
    task = Task.query.get_or_404(task_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para adicionar itens.'}), 403
        flash('Você não tem permissão para adicionar itens a esta tarefa.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    descricao = request.form.get('descricao', '').strip()
    status = request.form.get('status', 'programado')
    responsavel = request.form.get('responsavel', '').strip()
    
    # Validações
    if not descricao:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Descrição é obrigatória.'}), 400
        flash('Descrição é obrigatória.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    # Calcular ordem
    max_ordem = db.session.query(db.func.max(TaskItem.ordem)).filter_by(task_id=task_id).scalar() or 0
    
    # Criar item
    item = TaskItem(
        descricao=descricao,
        status=status,
        responsavel=responsavel if responsavel else None,
        task_id=task_id,
        ordem=max_ordem + 1
    )
    
    try:
        db.session.add(item)
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'item': {
                    'id': item.id,
                    'descricao': item.descricao,
                    'status': item.status,
                    'responsavel': item.responsavel or '',
                    'comments_count': 0
                }
            })
        flash('Item adicionado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao adicionar item: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/tarefas/itens/<int:item_id>/edit', methods=['POST'])
@login_required
def edit_task_item(item_id):
    """Edita item da tarefa"""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    descricao = request.form.get('descricao', '').strip()
    status = request.form.get('status', item.status)
    responsavel = request.form.get('responsavel', '').strip()
    
    # Validações
    if not descricao:
        return jsonify({'success': False, 'message': 'Descrição é obrigatória'}), 400
    
    # Atualizar item
    item.descricao = descricao
    item.status = status
    item.responsavel = responsavel if responsavel else None
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Item atualizado',
            'item': {
                'id': item.id,
                'descricao': item.descricao,
                'status': item.status,
                'responsavel': item.responsavel or ''
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/itens/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_task_item(item_id):
    """Exclui item da tarefa"""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    task_id = task.id
    
    # Verificar permissão
    can_delete = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_delete:
        flash('Você não tem permissão para excluir este item.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    try:
        db.session.delete(item)
        db.session.commit()
        flash('Item excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir item: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/tarefas/itens/<int:item_id>/update_status', methods=['POST'])
@login_required
def update_task_item_status(item_id):
    """Atualiza status do item via AJAX"""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    status = request.json.get('status')
    if status not in ['programado', 'em_andamento', 'validacao', 'finalizado']:
        return jsonify({'success': False, 'message': 'Status inválido'}), 400
    
    item.status = status
    
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Status atualizado'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/itens/reordenar', methods=['POST'])
@login_required
def reorder_task_items(task_id):
    """Reordena itens da tarefa"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    try:
        ordem_items = request.json.get('ordem', [])
        
        for index, item_id in enumerate(ordem_items, start=1):
            item = TaskItem.query.get(item_id)
            if item and item.task_id == task_id:
                item.ordem = index
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ordem atualizada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===================================
# COMENTÁRIOS EM ITENS DE TAREFA
# ===================================

def _can_comment_on_task(task):
    """Verifica se o usuário pode comentar na tarefa (e portanto nos itens)."""
    return (
        g.user.is_admin or
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )


@main_bp.route('/tarefas/itens/<int:item_id>/comentarios/add', methods=['POST'])
@login_required
def add_task_item_comment(item_id):
    """Adiciona comentário a um item (apenas após o item existir)."""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    if not _can_comment_on_task(task):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para comentar.'}), 403
        flash('Você não tem permissão para comentar neste item.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task.id))
    
    content = request.form.get('content', '').strip()
    if not content:
        if is_ajax:
            return jsonify({'success': False, 'message': 'O comentário não pode estar vazio.'}), 400
        flash('O comentário não pode estar vazio.', 'warning')
        return redirect(url_for('main.task_detail', task_id=task.id))
    
    comment = TaskItemComment(
        content=content,
        user_id=g.user.id,
        task_item_id=item_id
    )
    try:
        db.session.add(comment)
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'comment': {
                    'id': comment.id,
                    'content': comment.content,
                    'author_name': g.user.name,
                    'user_id': g.user.id,
                    'created_at': format_local_time(comment.created_at),
                    'is_own': True
                }
            })
        flash('Comentário adicionado.', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao adicionar comentário: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task.id))


@main_bp.route('/tarefas/comentarios/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_task_item_comment(comment_id):
    """Edita comentário (apenas o próprio autor)."""
    comment = TaskItemComment.query.get_or_404(comment_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    if comment.user_id != g.user.id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Você só pode editar seus próprios comentários.'}), 403
        flash('Você só pode editar seus próprios comentários.', 'danger')
        return redirect(url_for('main.task_detail', task_id=comment.task_item.task_id))
    
    content = request.form.get('content', '').strip()
    if not content:
        if is_ajax:
            return jsonify({'success': False, 'message': 'O comentário não pode estar vazio.'}), 400
        flash('O comentário não pode estar vazio.', 'warning')
        return redirect(url_for('main.task_detail', task_id=comment.task_item.task_id))
    
    comment.content = content
    comment.updated_at = datetime.datetime.utcnow()
    try:
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'comment': {
                    'id': comment.id,
                    'content': comment.content,
                    'updated_at': format_local_time(comment.updated_at) if comment.updated_at else None
                }
            })
        flash('Comentário atualizado.', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao atualizar comentário: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=comment.task_item.task_id))


@main_bp.route('/tarefas/comentarios/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_task_item_comment(comment_id):
    """Exclui comentário (apenas o próprio autor)."""
    comment = TaskItemComment.query.get_or_404(comment_id)
    task_id = comment.task_item.task_id
    
    if comment.user_id != g.user.id:
        flash('Você só pode excluir seus próprios comentários.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    try:
        db.session.delete(comment)
        db.session.commit()
        flash('Comentário excluído.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir comentário: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/projeto/<int:project_id>/tarefas', methods=['GET'])
@login_required
def project_tasks(project_id):
    """Lista tarefas de um projeto específico"""
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão de acesso ao projeto
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para acessar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))
    
    # Buscar tarefas do projeto
    tasks = Task.query.options(joinedload(Task.items)).filter_by(project_id=project_id).order_by(Task.created_at.desc()).all()
    
    return render_template('project_tasks.html', project=project, tasks=tasks)


@main_bp.route('/api/projetos_usuario', methods=['GET'])
@login_required
def get_user_projects_api():
    """API para obter projetos do usuário para dropdown"""
    if g.user.is_admin:
        projects = Project.query.order_by(Project.titulo).all()
    else:
        user_areas = g.user.get_areas()
        projects = Project.query.filter(Project.area_responsavel.in_(user_areas)).order_by(Project.titulo).all()
    
    return jsonify([
        {
            'id': p.id,
            'titulo': p.titulo,
            'area_responsavel': p.area_responsavel
        }
        for p in projects
    ])


@main_bp.route('/tarefas/<int:task_id>/sugestoes-responsavel', methods=['GET'])
@login_required
def get_task_assignable_users(task_id):
    """API: usuários que podem ser marcados como responsável no item (pessoas do projeto). Se a tarefa não tem projeto, retorna lista vazia."""
    task = Task.query.get_or_404(task_id)
    if not task.project_id or not task.project:
        return jsonify({'users': []})
    area = task.project.area_responsavel
    if not area:
        return jsonify({'users': []})
    # Usuários que têm essa área (UserArea ou area_responsavel legado)
    user_ids_area = [ua.user_id for ua in UserArea.query.filter_by(area=area).all()]
    if user_ids_area:
        users_q = User.query.filter(User.id.in_(user_ids_area)).order_by(User.name)
    else:
        users_q = User.query.filter(User.area_responsavel == area).order_by(User.name)
    users = [{'id': u.id, 'name': u.name} for u in users_q.all()]
    q = (request.args.get('q') or '').strip().lower()
    if q:
        users = [u for u in users if q in (u['name'] or '').lower()]
    return jsonify({'users': users})
