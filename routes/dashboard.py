import datetime

from flask import g, render_template
from sqlalchemy import and_, or_

from models import Etapa, Project, Task, db

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

    for projeto in projetos_vigentes_query.all():
        if Etapa.query.filter(Etapa.project_id == projeto.id, Etapa.done == False, Etapa.data_fim < data_atual).count() > 0:
            projetos_em_atraso += 1

    objetivos, _, _ = get_goal_catalog_context()

    def apply_task_visibility_rules(query, include_archived=False):
        if not include_archived:
            query = query.filter(Task.is_archived.is_(False))

        if g.user.is_admin:
            return query

        user_areas = g.user.get_areas()
        visibility_filters = [
            and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)
        ]
        if user_areas:
            visibility_filters.insert(
                0,
                and_(
                    Task.project_id.isnot(None),
                    Project.area_responsavel.in_(user_areas)
                )
            )

        return query.outerjoin(Project, Task.project_id == Project.id).filter(or_(*visibility_filters))

    open_tasks_count_query = db.session.query(db.func.count(Task.id)).select_from(Task).filter(Task.status != 'finalizado')
    open_tasks_count_query = apply_task_visibility_rules(open_tasks_count_query, include_archived=False)
    dashboard_open_tasks_count = int(open_tasks_count_query.scalar() or 0)

    # Mantido por compatibilidade com template atual.
    dashboard_open_items_count = dashboard_open_tasks_count

    def count_tasks_by_status(status_value):
        q = db.session.query(db.func.count(Task.id)).select_from(Task).filter(Task.status == status_value)
        q = apply_task_visibility_rules(q, include_archived=False)
        return int(q.scalar() or 0)

    task_items_programado = count_tasks_by_status('programado')
    task_items_em_andamento = count_tasks_by_status('em_andamento')
    task_items_validacao = count_tasks_by_status('validacao')
    task_items_finalizado = count_tasks_by_status('finalizado')
    task_items_total = task_items_programado + task_items_em_andamento + task_items_validacao + task_items_finalizado

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
        task_items_programado=task_items_programado,
        task_items_em_andamento=task_items_em_andamento,
        task_items_validacao=task_items_validacao,
        task_items_finalizado=task_items_finalizado,
        task_items_total=task_items_total,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES,
    )
