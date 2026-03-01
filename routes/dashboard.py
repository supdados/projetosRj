import datetime

from flask import g, render_template, request
from sqlalchemy import and_, or_

from models import Etapa, Project, Task, db

from .blueprint import main_bp
from .decorators import login_required
from .shared import get_area_catalog_choices, get_goal_catalog_context


@main_bp.route('/dashboard')
@login_required
def dashboard():
    selected_area = (request.args.get('area') or '').strip()

    project_query_base = Project.query
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if user_areas:
            project_query_base = project_query_base.filter(Project.area_responsavel.in_(user_areas))
    if selected_area:
        project_query_base = project_query_base.filter(Project.area_responsavel == selected_area)

    RECENT_PROJECTS_LIMIT = 15
    recent_projects = project_query_base.order_by(Project.id.desc()).limit(RECENT_PROJECTS_LIMIT).all()

    def count_projects_for_user(filter_expression=None):
        query = Project.query
        if not g.user.is_admin:
            user_areas = g.user.get_areas()
            if user_areas:
                query = query.filter(Project.area_responsavel.in_(user_areas))
        if selected_area:
            query = query.filter(Project.area_responsavel == selected_area)
        if filter_expression is not None:
            query = query.filter(filter_expression)
        return query.count()

    count_urgente = count_projects_for_user(Project.prioridade == 'urgente')
    count_alta = count_projects_for_user(Project.prioridade == 'alta')
    count_media = count_projects_for_user(Project.prioridade == 'media')
    count_baixa = count_projects_for_user(Project.prioridade == 'baixa')
    count_vigente = count_projects_for_user(Project.status == 'Vigente')
    count_finalizado = count_projects_for_user(Project.status == 'Finalizado')
    num_projects = count_projects_for_user()

    data_atual = datetime.date.today()
    projetos_em_atraso = 0

    projetos_vigentes_query = Project.query.filter(Project.status == 'Vigente')
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if user_areas:
            projetos_vigentes_query = projetos_vigentes_query.filter(Project.area_responsavel.in_(user_areas))
    if selected_area:
        projetos_vigentes_query = projetos_vigentes_query.filter(Project.area_responsavel == selected_area)

    for projeto in projetos_vigentes_query.all():
        if Etapa.query.filter(Etapa.project_id == projeto.id, Etapa.done == False, Etapa.data_fim < data_atual).count() > 0:
            projetos_em_atraso += 1

    objetivos, _, _ = get_goal_catalog_context()
    area_catalog_choices = get_area_catalog_choices()

    def apply_task_visibility_rules(query, include_archived=False):
        if not include_archived:
            query = query.filter(Task.is_archived.is_(False))

        if g.user.is_admin:
            if selected_area:
                query = query.outerjoin(Project, Task.project_id == Project.id).filter(
                    Task.project_id.isnot(None),
                    Project.area_responsavel == selected_area,
                )
            return query

        user_areas = g.user.get_areas()
        if selected_area and user_areas:
            effective_areas = [selected_area] if selected_area in user_areas else []
        else:
            effective_areas = user_areas

        visibility_filters = [
            and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)
        ]
        if effective_areas:
            visibility_filters.insert(
                0,
                and_(
                    Task.project_id.isnot(None),
                    Project.area_responsavel.in_(effective_areas)
                )
            )

        return query.outerjoin(Project, Task.project_id == Project.id).filter(or_(*visibility_filters))

    open_tasks_count_query = db.session.query(db.func.count(Task.id)).select_from(Task).filter(Task.status != 'finalizada')
    open_tasks_count_query = apply_task_visibility_rules(open_tasks_count_query, include_archived=False)
    dashboard_open_tasks_count = int(open_tasks_count_query.scalar() or 0)

    dashboard_open_items_count = dashboard_open_tasks_count

    def count_tasks_by_status(status_value):
        q = db.session.query(db.func.count(Task.id)).select_from(Task).filter(Task.status == status_value)
        q = apply_task_visibility_rules(q, include_archived=False)
        return int(q.scalar() or 0)

    task_items_nao_iniciada = count_tasks_by_status('nao_iniciada')
    task_items_em_andamento = count_tasks_by_status('em_andamento')
    task_items_para_validacao = count_tasks_by_status('para_validacao')
    task_items_para_ajustes = count_tasks_by_status('para_ajustes')
    task_items_finalizada = count_tasks_by_status('finalizada')
    task_items_total = task_items_nao_iniciada + task_items_em_andamento + task_items_para_validacao + task_items_para_ajustes + task_items_finalizada

    def count_open_tasks_by_priority(prioridade_value):
        if prioridade_value is None:
            q = db.session.query(db.func.count(Task.id)).select_from(Task).filter(
                Task.prioridade.is_(None),
                Task.status != 'finalizada',
            )
        else:
            q = db.session.query(db.func.count(Task.id)).select_from(Task).filter(
                Task.prioridade == prioridade_value,
                Task.status != 'finalizada',
            )
        q = apply_task_visibility_rules(q, include_archived=False)
        return int(q.scalar() or 0)

    task_urgente_count = count_open_tasks_by_priority('urgente')
    task_alta_count = count_open_tasks_by_priority('alta')
    task_media_count = count_open_tasks_by_priority('media')
    task_baixa_count = count_open_tasks_by_priority('baixa')
    task_atencao_count = task_items_para_validacao + task_items_para_ajustes

    recent_tasks_q = Task.query.filter(Task.status != 'finalizada')
    recent_tasks_q = apply_task_visibility_rules(recent_tasks_q, include_archived=False)
    recent_tasks = recent_tasks_q.order_by(Task.id.desc()).limit(9).all()

    dashboard_tasks = []
    dashboard_tasks_pagination = {
        'page': 1,
        'per_page': 0,
        'total': 0,
        'total_pages': 1,
        'has_prev': False,
        'has_next': False,
        'prev_url': None,
        'next_url': None,
    }

    return render_template(
        'index.html',
        recent_projects=recent_projects,
        count_urgente=count_urgente,
        count_alta=count_alta,
        count_media=count_media,
        count_baixa=count_baixa,
        count_vigente=count_vigente,
        count_finalizado=count_finalizado,
        num_projects=num_projects,
        projetos_em_atraso=projetos_em_atraso,
        dashboard_tasks=dashboard_tasks,
        dashboard_open_tasks_count=dashboard_open_tasks_count,
        dashboard_open_items_count=dashboard_open_items_count,
        dashboard_tasks_pagination=dashboard_tasks_pagination,
        task_items_nao_iniciada=task_items_nao_iniciada,
        task_items_em_andamento=task_items_em_andamento,
        task_items_para_validacao=task_items_para_validacao,
        task_items_para_ajustes=task_items_para_ajustes,
        task_items_finalizada=task_items_finalizada,
        task_items_total=task_items_total,
        task_urgente_count=task_urgente_count,
        task_alta_count=task_alta_count,
        task_media_count=task_media_count,
        task_baixa_count=task_baixa_count,
        task_atencao_count=task_atencao_count,
        recent_tasks=recent_tasks,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=area_catalog_choices,
    )
