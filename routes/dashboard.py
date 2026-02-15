import datetime

from flask import g, render_template

from models import Etapa, Project

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
