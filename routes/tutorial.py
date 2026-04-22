from flask import flash, g, jsonify, redirect, render_template, request, session, url_for

from models import Project, db

from .blueprint import main_bp
from .decorators import login_required

_SECTION_START_URLS = {
    'criar_projeto': lambda _project_id: url_for('main.dashboard'),
    'explorar_projeto': lambda project_id: url_for('main.project_detail', project_id=project_id),
    'criar_etapa': lambda project_id: url_for('main.project_detail', project_id=project_id),
    'criar_tarefa': lambda project_id: url_for('main.project_tasks', project_id=project_id),
    'navegar': lambda _project_id: url_for('main.dashboard'),
}

_SECTIONS_NEEDING_PROJECT = {'explorar_projeto', 'criar_etapa', 'criar_tarefa'}


def _get_or_create_tutorial_project() -> Project:
    """Retorna projeto tutorial existente ou cria um novo para o usuário atual."""
    existing = Project.query.filter_by(is_tutorial=True).first()
    if existing:
        return existing

    areas = g.user.get_areas()
    area = areas[0] if areas else None
    project = Project(
        titulo='[Tutorial] Projeto de Demonstração',
        area_responsavel=area,
        orgao=g.user.orgao,
        prioridade='media',
        status='Vigente',
        is_tutorial=True,
        observacao='Projeto criado automaticamente pelo tutorial. Pode ser apagado ao final.',
    )
    db.session.add(project)
    db.session.commit()
    return project


@main_bp.route('/tutorial/begin')
@login_required
def tutorial_begin():
    """Inicia o tutorial do zero, sempre da seção 1. Chamado pelo ícone no topnav."""
    session['tutorial_active'] = True
    session['tutorial_section'] = 'criar_projeto'
    return redirect(url_for('main.dashboard'))


@main_bp.route('/tutorial')
@login_required
def tutorial_index():
    has_tutorial_projects = Project.query.filter_by(is_tutorial=True).count() > 0
    return render_template(
        'tutorial/index.html',
        has_tutorial_projects=has_tutorial_projects,
        tutorial_active=session.get('tutorial_active', False),
    )


@main_bp.route('/tutorial/start', methods=['POST'])
@login_required
def tutorial_start():
    section = request.form.get('section', 'criar_projeto')
    if section not in _SECTION_START_URLS:
        section = 'criar_projeto'

    session['tutorial_active'] = True
    session['tutorial_section'] = section

    project_id = None
    if section in _SECTIONS_NEEDING_PROJECT:
        project = _get_or_create_tutorial_project()
        project_id = project.id

    start_url = _SECTION_START_URLS[section](project_id)
    return redirect(start_url)


@main_bp.route('/tutorial/pause', methods=['POST'])
@login_required
def tutorial_pause():
    session.pop('tutorial_active', None)
    return ('', 204) if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else redirect(request.referrer or url_for('main.dashboard'))


@main_bp.route('/tutorial/finish', methods=['POST'])
@login_required
def tutorial_finish():
    session.pop('tutorial_active', None)
    session.pop('tutorial_section', None)
    has_data = Project.query.filter_by(is_tutorial=True).count() > 0
    return render_template('tutorial/finish.html', has_tutorial_data=has_data)


@main_bp.route('/tutorial/finish-redirect')
@login_required
def tutorial_finish_redirect():
    """Destino de navegação após o runner encerrar o último step via JS."""
    session.pop('tutorial_active', None)
    session.pop('tutorial_section', None)
    has_data = Project.query.filter_by(is_tutorial=True).count() > 0
    return render_template('tutorial/finish.html', has_tutorial_data=has_data)


@main_bp.route('/tutorial/cleanup', methods=['POST'])
@login_required
def tutorial_cleanup():
    projects = Project.query.filter_by(is_tutorial=True).all()
    count = len(projects)
    for p in projects:
        db.session.delete(p)
    db.session.commit()
    flash(f'{count} projeto(s) de demonstração apagado(s).', 'success')
    return redirect(url_for('main.tutorial_index'))


@main_bp.route('/tutorial/dismiss', methods=['POST'])
@login_required
def tutorial_dismiss():
    """Marca tutorial como visto para o usuário (fecha modal de boas-vindas)."""
    g.user.tutorial_visto = True
    db.session.commit()
    return ('', 204) if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else redirect(url_for('main.dashboard'))
