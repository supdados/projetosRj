import datetime

from flask import g, render_template, request, url_for

from models import Etapa, Project, Task, TaskItem, db

from .blueprint import main_bp
from .decorators import login_required
from .shared import AREAS_RESPONSAVEIS_CHOICES, get_goal_catalog_context


@main_bp.route('/dashboard')
@login_required
def dashboard():
    project_query_base = Project.query
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if user_areas:
            project_query_base = project_query_base.filter(Project.area_responsavel.in_(user_areas))

    RECENT_PROJECTS_LIMIT = 9
    recent_projects = project_query_base.order_by(Project.id.desc()).limit(RECENT_PROJECTS_LIMIT).all()
    
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

    open_item_counts_subquery = (
        db.session.query(
            TaskItem.task_id.label('task_id'),
            db.func.count(TaskItem.id).label('open_items_count')
        )
        .filter(TaskItem.status != 'finalizado')
        .group_by(TaskItem.task_id)
        .subquery()
    )

    def apply_task_visibility_rules(query, include_finalized=False):
        if not include_finalized:
            query = query.filter(Task.is_finalized.is_(False))

        if g.user.is_admin:
            return query

        user_areas = g.user.get_areas()
        visibility_filters = [
            db.and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)
        ]
        if user_areas:
            visibility_filters.insert(
                0,
                db.and_(
                    Task.project_id.isnot(None),
                    Project.area_responsavel.in_(user_areas)
                )
            )

        return query.outerjoin(Project, Task.project_id == Project.id).filter(db.or_(*visibility_filters))

    open_tasks_count_query = db.session.query(db.func.count(Task.id)).select_from(Task).join(
        open_item_counts_subquery,
        open_item_counts_subquery.c.task_id == Task.id
    )
    open_tasks_count_query = apply_task_visibility_rules(open_tasks_count_query)
    dashboard_open_tasks_count = int(open_tasks_count_query.scalar() or 0)

    open_items_count_query = db.session.query(
        db.func.coalesce(db.func.sum(open_item_counts_subquery.c.open_items_count), 0)
    ).select_from(Task).join(
        open_item_counts_subquery,
        open_item_counts_subquery.c.task_id == Task.id
    )
    open_items_count_query = apply_task_visibility_rules(open_items_count_query)
    dashboard_open_items_count = int(open_items_count_query.scalar() or 0)

    # Task items count by status for KPI dashboard
    def count_task_items_by_status(status_value):
        q = db.session.query(db.func.count(TaskItem.id)).select_from(TaskItem).join(
            Task, TaskItem.task_id == Task.id
        ).filter(TaskItem.status == status_value)
        q = apply_task_visibility_rules(q)
        return int(q.scalar() or 0)

    task_items_programado = count_task_items_by_status('programado')
    task_items_em_andamento = count_task_items_by_status('em_andamento')
    task_items_validacao = count_task_items_by_status('validacao')
    task_items_finalizado = count_task_items_by_status('finalizado')
    task_items_total = task_items_programado + task_items_em_andamento + task_items_validacao + task_items_finalizado

    tasks_page = request.args.get('tasks_page', 1, type=int) or 1
    if tasks_page < 1:
        tasks_page = 1

    dashboard_tasks_rows = db.session.query(
        Task,
        open_item_counts_subquery.c.open_items_count
    ).join(
        open_item_counts_subquery,
        open_item_counts_subquery.c.task_id == Task.id
    )
    dashboard_tasks_rows = apply_task_visibility_rules(dashboard_tasks_rows).order_by(
        open_item_counts_subquery.c.open_items_count.desc(),
        Task.created_at.desc()
    ).all()

    tasks_page_base_args = request.args.to_dict(flat=True)
    tasks_page_base_args.pop('tasks_page', None)

    def build_tasks_page_url(page_number):
        page_args = dict(tasks_page_base_args)
        if page_number > 1:
            page_args['tasks_page'] = page_number
        return url_for('main.dashboard', **page_args)

    status_labels = {
        'programado': 'Programado',
        'em_andamento': 'Em andamento',
        'validacao': 'Validação',
        'finalizado': 'Finalizado'
    }
    MAX_PREVIEW_ITEMS_TOTAL = 6
    MAX_PREVIEW_ITEMS_PER_TASK = 3
    dashboard_tasks = []
    ordered_tasks = []
    for task, open_items_count in dashboard_tasks_rows:
        preview_capacity = min(int(open_items_count or 0), MAX_PREVIEW_ITEMS_PER_TASK)
        if preview_capacity <= 0:
            continue
        ordered_tasks.append({
            'task': task,
            'open_items_count': int(open_items_count or 0),
            'preview_capacity': preview_capacity
        })

    pages = []
    current_page = []
    remaining_slots = MAX_PREVIEW_ITEMS_TOTAL

    for task_data in ordered_tasks:
        capacity = task_data['preview_capacity']
        if current_page and capacity > remaining_slots:
            pages.append(current_page)
            current_page = []
            remaining_slots = MAX_PREVIEW_ITEMS_TOTAL

        current_page.append(task_data)
        remaining_slots -= capacity

        if remaining_slots == 0:
            pages.append(current_page)
            current_page = []
            remaining_slots = MAX_PREVIEW_ITEMS_TOTAL

    if current_page:
        pages.append(current_page)

    dashboard_tasks_total = len(ordered_tasks)
    dashboard_tasks_total_pages = max(1, len(pages)) if dashboard_tasks_total else 1
    tasks_page = min(tasks_page, dashboard_tasks_total_pages)
    selected_page_tasks = pages[tasks_page - 1] if pages else []

    for task_data in selected_page_tasks:
        task = task_data['task']
        open_items_query = (
            TaskItem.query
            .filter(
                TaskItem.task_id == task.id,
                TaskItem.status != 'finalizado'
            )
            .order_by(TaskItem.ordem.asc(), TaskItem.created_at.asc())
            .limit(MAX_PREVIEW_ITEMS_PER_TASK)
            .all()
        )
        items_preview = []
        for item in open_items_query[:task_data['preview_capacity']]:
            items_preview.append({
                'item_id': item.id,
                'descricao': item.descricao,
                'status': item.status,
                'status_label': status_labels.get(item.status, item.status),
                'responsavel': item.responsavel
            })

        dashboard_tasks.append({
            'task_id': task.id,
            'titulo': task.titulo,
            'project_id': task.project_id,
            'project_titulo': task.project.titulo if task.project else None,
            'open_items_count': task_data['open_items_count'],
            'items_preview': items_preview
        })

    dashboard_tasks_pagination = {
        'page': tasks_page,
        'per_page': MAX_PREVIEW_ITEMS_TOTAL,
        'total': dashboard_tasks_total,
        'total_pages': dashboard_tasks_total_pages,
        'has_prev': tasks_page > 1,
        'has_next': tasks_page < dashboard_tasks_total_pages,
        'prev_url': build_tasks_page_url(tasks_page - 1) if tasks_page > 1 else None,
        'next_url': build_tasks_page_url(tasks_page + 1) if tasks_page < dashboard_tasks_total_pages else None
    }
    
    return render_template(
        'index.html', 
        recent_projects=recent_projects,
        count_urgente=count_urgente, count_alta=count_alta,
        count_media=count_media, count_baixa=count_baixa,
        count_vigente=count_vigente, count_finalizado=count_finalizado, num_projects=num_projects,
        projetos_em_atraso=projetos_em_atraso,
        dashboard_tasks=dashboard_tasks,
        dashboard_open_tasks_count=dashboard_open_tasks_count,
        dashboard_open_items_count=dashboard_open_items_count,
        dashboard_tasks_pagination=dashboard_tasks_pagination,
        task_items_programado=task_items_programado,
        task_items_em_andamento=task_items_em_andamento,
        task_items_validacao=task_items_validacao,
        task_items_finalizado=task_items_finalizado,
        task_items_total=task_items_total,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES # Para o modal
    )
