from flask import flash, g, redirect, render_template, request, session, url_for

from models import Project, db

from .blueprint import main_bp
from .decorators import login_required

_SECTION_START_URLS = {
    'criar_projeto':    lambda _pid: url_for('main.dashboard'),
    'criar_etapa':      lambda pid: url_for('main.project_detail', project_id=pid),
    'explorar_projeto': lambda pid: url_for('main.project_detail', project_id=pid),
    'criar_tarefa':     lambda _pid: url_for('main.list_tasks'),
    'navegar':          lambda _pid: url_for('main.dashboard'),
}

# Seções que precisam de um projeto criado pelo usuário durante o tutorial
_SECTIONS_NEEDING_PROJECT = {'criar_etapa', 'explorar_projeto'}


def _get_tutorial_project_id() -> int | None:
    """Retorna o ID do projeto criado pelo usuário durante o tutorial."""
    pid = session.get('tutorial_project_id')
    if pid:
        return pid
    # Fallback: projeto mais recente marcado como tutorial
    p = Project.query.filter_by(is_tutorial=True).order_by(Project.id.desc()).first()
    return p.id if p else None


@main_bp.route('/tutorial/begin')
@login_required
def tutorial_begin():
    """Inicia o tutorial do zero. Chamado pelo ícone no topnav."""
    session['tutorial_active'] = True
    session['tutorial_section'] = 'criar_projeto'
    session['tutorial_reset'] = True
    session.pop('tutorial_project_id', None)
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
        project_id = _get_tutorial_project_id()
        if not project_id:
            flash('Crie um projeto primeiro para continuar o tutorial.', 'info')
            session['tutorial_section'] = 'criar_projeto'
            return redirect(url_for('main.dashboard'))

    return redirect(_SECTION_START_URLS[section](project_id))


@main_bp.route('/tutorial/pause', methods=['POST'])
@login_required
def tutorial_pause():
    session.pop('tutorial_active', None)
    session['tutorial_reset'] = True   # garante que o próximo início recomece do zero
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
    """Destino de navegação após o runner JS encerrar o último step."""
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
    session.pop('tutorial_project_id', None)
    flash(f'{count} projeto(s) de demonstração apagado(s).', 'success')
    return redirect(url_for('main.tutorial_index'))


@main_bp.route('/tutorial/dismiss', methods=['POST'])
@login_required
def tutorial_dismiss():
    """Marca tutorial como visto para o usuário (fecha modal de boas-vindas)."""
    g.user.tutorial_visto = True
    db.session.commit()
    return ('', 204) if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else redirect(url_for('main.dashboard'))
