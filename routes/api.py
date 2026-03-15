from flask import g, jsonify

from models import Project, StageTemplate
from catalogs.objectives import (
    OBJETIVO_IDS,
    RESULTADO_IDS,
    get_indicadores_for_resultado,
    get_resultados_for_objetivo,
)

from .blueprint import main_bp
from .decorators import login_required
from .shared import get_or_404
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
    template = get_or_404(StageTemplate, template_id)
    stages = [{'name': item.name, 'order': item.order, 'duration': item.duration_days} for item in template.items]
    return jsonify(stages)
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
