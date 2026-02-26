import datetime
import os
import re
import uuid
from urllib.parse import urlparse

from flask import flash, g, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload

from models import Project, Task, TaskItem, TaskItemAnexo, TaskItemComment, User, UserArea, db
from services.notifications import notify_task_assignment_change, notify_task_event

from .blueprint import main_bp
from .decorators import login_required
from .shared import format_local_time

VALID_PRIORIDADES = {'baixa', 'media', 'alta', 'urgente'}
VALID_TIPOS = {'bug', 'melhoria', 'duvida', 'outros'}
LEGACY_TIPOS = {'implementacao'}
VALID_STATUSES = {'programado', 'em_andamento', 'validacao', 'finalizado'}
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}


def _get_upload_folder():
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    folder = os.path.join(basedir, 'instance', 'uploads', 'task_items')
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _can_view_task(user, task):
    """Regra unificada de visualização/edição da tarefa."""
    return (
        user.is_admin or
        task.created_by_id == user.id or
        (task.project_id and task.project and task.project.area_responsavel in user.get_areas())
    )


def _task_item_status_label(status):
    status_labels = {
        'programado': 'Programado',
        'em_andamento': 'Em andamento',
        'validacao': 'Validacao',
        'finalizado': 'Finalizado',
    }
    return status_labels.get(status, status or '')


def _preview_text(value, max_length=90):
    text_value = ' '.join((value or '').split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + '...'


def _normalize_person_name(name):
    """Normaliza nome para comparação (trim + colapso de espaços)."""
    return ' '.join((name or '').strip().split())


def _split_responsavel_names(raw_value):
    """Quebra string de responsáveis em nomes únicos preservando ordem."""
    raw_value = (raw_value or '').replace('\r', '\n').strip()
    if not raw_value:
        return []

    names = []
    seen = set()

    for part in re.split(r'[,\n;]+', raw_value):
        normalized = _normalize_person_name(part.lstrip('@'))
        if not normalized:
            continue

        key = normalized.casefold()
        if key in seen:
            continue

        seen.add(key)
        names.append(normalized)

    return names


def _normalize_responsavel_value(raw_value):
    """Normaliza valor completo para comparação semântica."""
    return ', '.join(_split_responsavel_names(raw_value))


def _get_task_assignable_users(task):
    """Retorna usuários elegíveis para o campo responsável com base na regra de visualização."""
    candidate_ids = set()

    if task.created_by_id:
        candidate_ids.add(task.created_by_id)

    admin_ids = [user_id for (user_id,) in User.query.with_entities(User.id).filter(User.is_admin.is_(True)).all()]
    candidate_ids.update(admin_ids)

    area = task.project.area_responsavel if task.project_id and task.project else None
    if area:
        area_user_ids = [user_id for (user_id,) in UserArea.query.with_entities(UserArea.user_id).filter_by(area=area).all()]
        candidate_ids.update(area_user_ids)

        legacy_area_ids = [user_id for (user_id,) in User.query.with_entities(User.id).filter(User.area_responsavel == area).all()]
        candidate_ids.update(legacy_area_ids)

    if not candidate_ids:
        return []

    return User.query.filter(User.id.in_(candidate_ids)).order_by(User.name.asc()).all()


def _validate_task_item_responsavel(task, raw_value):
    """Valida responsáveis contra usuários elegíveis e retorna nomes canônicos."""
    parsed_names = _split_responsavel_names(raw_value)
    if not parsed_names:
        return True, '', []

    allowed_users = _get_task_assignable_users(task)
    allowed_by_key = {}

    for user in allowed_users:
        canonical_name = _normalize_person_name(user.name)
        if canonical_name:
            allowed_by_key[canonical_name.casefold()] = canonical_name

    canonical_names = []
    invalid_names = []
    seen_canonical = set()

    for name in parsed_names:
        canonical = allowed_by_key.get(name.casefold())
        if not canonical:
            invalid_names.append(name)
            continue

        canonical_key = canonical.casefold()
        if canonical_key in seen_canonical:
            continue

        seen_canonical.add(canonical_key)
        canonical_names.append(canonical)

    return len(invalid_names) == 0, ', '.join(canonical_names), invalid_names


def _format_invalid_responsavel_message(invalid_names):
    invalid_str = ', '.join(invalid_names)
    return f'Responsável inválido: {invalid_str}. Selecione somente usuários com permissão de visualização.'


def _resolve_responsavel_for_item_edit(item, incoming_raw_value):
    """
    Compatibilidade de legado:
    - Se valor semântico não mudou, mantém valor atual mesmo que legado inválido.
    - Se mudou, aplica validação estrita.
    """
    current_normalized = _normalize_responsavel_value(item.responsavel or '')
    incoming_normalized = _normalize_responsavel_value(incoming_raw_value)

    if incoming_normalized == current_normalized:
        return True, (item.responsavel or ''), []

    return _validate_task_item_responsavel(item.task, incoming_raw_value)


def _build_task_visibility_query(show_finalized, include_relations=True):
    """Monta query base de tarefas visíveis ao usuário para estado ativo/finalizado."""
    query = Task.query
    if include_relations:
        query = query.options(joinedload(Task.items), joinedload(Task.project))

    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        visibility_filters = [db.and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)]
        if user_areas:
            visibility_filters.insert(
                0,
                db.and_(Task.project_id.isnot(None), Project.area_responsavel.in_(user_areas))
            )
        query = query.outerjoin(Project).filter(db.or_(*visibility_filters))

    return query.filter(Task.is_finalized.is_(show_finalized))


def _apply_task_listing_filters(query, project_filter='', search_query=''):
    """Aplica filtros de projeto e busca de título na listagem de tarefas."""
    if project_filter:
        if project_filter == 'sem_projeto':
            query = query.filter(Task.project_id.is_(None))
        else:
            try:
                project_id = int(project_filter)
            except (TypeError, ValueError):
                return query.filter(db.false())
            query = query.filter(Task.project_id == project_id)

    if search_query:
        query = query.filter(Task.titulo.ilike(f'%{search_query}%'))

    return query


def _get_projects_for_task_filter():
    if g.user.is_admin:
        return Project.query.order_by(Project.titulo).all()
    user_areas = g.user.get_areas()
    return Project.query.filter(Project.area_responsavel.in_(user_areas)).order_by(Project.titulo).all()


def _resolve_task_hub_area_scope(selected_area):
    """Resolve escopo de área permitido para o hub de itens."""
    area = (selected_area or '').strip()

    if g.user.is_admin:
        if area:
            return [area], area
        return None, ''

    user_areas = g.user.get_areas()
    if not user_areas:
        return [], area

    if area:
        if area in user_areas:
            return [area], area
        return [], area

    return user_areas, ''


def _build_task_items_hub_query(selected_area='', project_filter=''):
    """Monta query de itens ativos visíveis no hub /tarefas."""
    area_scope, normalized_area = _resolve_task_hub_area_scope(selected_area)

    query = (
        TaskItem.query
        .options(
            joinedload(TaskItem.task).joinedload(Task.project),
            joinedload(TaskItem.comments),
            joinedload(TaskItem.anexos),
        )
        .join(Task, TaskItem.task_id == Task.id)
        .outerjoin(Project, Task.project_id == Project.id)
        .filter(Task.is_finalized.is_(False))
    )

    if g.user.is_admin:
        # Admin vê tudo quando não há filtro de área.
        pass
    else:
        visibility_filters = [db.and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)]
        if area_scope:
            visibility_filters.insert(
                0,
                db.and_(Task.project_id.isnot(None), Project.area_responsavel.in_(area_scope)),
            )
        query = query.filter(db.or_(*visibility_filters))

    if normalized_area:
        query = query.filter(
            Task.project_id.isnot(None),
            Project.area_responsavel == normalized_area,
        )

    if project_filter:
        if project_filter == 'sem_projeto':
            query = query.filter(Task.project_id.is_(None))
        else:
            try:
                project_id = int(project_filter)
            except (TypeError, ValueError):
                return query.filter(db.false())
            query = query.filter(Task.project_id == project_id)

    return query.order_by(
        Project.titulo.asc(),
        Task.created_at.asc(),
        Task.id.asc(),
        TaskItem.ordem.asc(),
        TaskItem.id.asc(),
    )


def _group_hub_items_by_project(items):
    """Agrupa itens visíveis por projeto para renderização do hub."""
    groups = {}

    for item in items:
        task = item.task
        project = task.project if task else None
        project_id = project.id if project else None
        project_title = (project.titulo if project else 'Sem projeto') or 'Sem projeto'
        project_area = project.area_responsavel if project else None
        project_value = str(project_id) if project_id else 'sem_projeto'
        group_key = f'project:{project_id}' if project_id else 'sem_projeto'

        if group_key not in groups:
            groups[group_key] = {
                'key': group_key,
                'project_id': project_id,
                'project_value': project_value,
                'project_titulo': project_title,
                'project_area': project_area,
                'items': [],
                'task_ids': set(),
            }

        # Metadados de contexto usados no template/JS do hub.
        item.hub_project_value = project_value
        item.hub_project_titulo = project_title
        item.hub_task_titulo = task.titulo if task else ''
        item.hub_task_id = task.id if task else None

        groups[group_key]['items'].append(item)
        if task:
            groups[group_key]['task_ids'].add(task.id)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            group['project_id'] is None,  # "Sem projeto" sempre ao final.
            (group['project_titulo'] or '').casefold(),
        ),
    )

    for group in ordered_groups:
        group['task_count'] = len(group['task_ids'])

    return ordered_groups


def _build_task_hub_area_options():
    """Lista áreas disponíveis para o seletor do hub."""
    if g.user.is_admin:
        rows = (
            db.session.query(Project.area_responsavel)
            .join(Task, Task.project_id == Project.id)
            .join(TaskItem, TaskItem.task_id == Task.id)
            .filter(
                Task.is_finalized.is_(False),
                Project.area_responsavel.isnot(None),
            )
            .distinct()
            .all()
        )
        return sorted({(area or '').strip() for (area,) in rows if (area or '').strip()})

    return sorted({area for area in g.user.get_areas() if area})


def _render_task_hub():
    """Renderiza o novo hub de itens da rota /tarefas."""
    selected_area = (request.args.get('area') or '').strip()
    project_filter = (request.args.get('project') or '').strip()

    items = _build_task_items_hub_query(
        selected_area=selected_area,
        project_filter=project_filter,
    ).all()
    groups = _group_hub_items_by_project(items)

    filter_scope_items = _build_task_items_hub_query(
        selected_area=selected_area,
        project_filter='',
    ).all()
    filter_scope_groups = _group_hub_items_by_project(filter_scope_items)

    project_options = [
        {
            'value': group['project_value'],
            'label': group['project_titulo'],
            'area': group['project_area'],
        }
        for group in filter_scope_groups
    ]

    project_label_map = {opt['value']: opt['label'] for opt in project_options}
    selected_project_label = project_label_map.get(project_filter, '')
    if not selected_project_label and project_filter == 'sem_projeto':
        selected_project_label = 'Sem projeto'

    user_areas = g.user.get_areas()
    show_area_selector = g.user.is_admin or len(user_areas) > 1
    area_options = _build_task_hub_area_options() if show_area_selector else []

    return render_template(
        'task_hub.html',
        groups=groups,
        project_options=project_options,
        selected_project=project_filter,
        selected_project_label=selected_project_label,
        selected_area=selected_area,
        area_options=area_options,
        show_area_selector=show_area_selector,
        total_items=len(items),
    )


def _get_safe_next_url():
    raw_next = (
        request.form.get('next')
        or request.args.get('next')
        or request.headers.get('Referer')
        or request.referrer
    )
    if not raw_next:
        return None

    parsed = urlparse(raw_next)

    # Relative internal URL
    if not parsed.netloc and parsed.path.startswith('/'):
        target = parsed.path
        if parsed.query:
            target = f'{target}?{parsed.query}'
        return target

    # Absolute URL only if same host
    if parsed.netloc and parsed.netloc == request.host:
        target = parsed.path or '/'
        if parsed.query:
            target = f'{target}?{parsed.query}'
        return target

    return None


def _redirect_back_or(default_endpoint):
    next_url = _get_safe_next_url()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(default_endpoint))


def _render_tasks_listing(show_finalized):
    """Renderiza listagem de tarefas (ativas ou finalizadas) com filtros e paginação."""
    project_filter = request.args.get('project', '')
    search_query = (request.args.get('search', '') or '').strip()
    page = request.args.get('page', 1, type=int) or 1
    if page < 1:
        page = 1

    query = _apply_task_listing_filters(
        _build_task_visibility_query(show_finalized=show_finalized),
        project_filter=project_filter,
        search_query=search_query,
    )

    if show_finalized:
        query = query.order_by(Task.finalized_at.desc(), Task.created_at.desc())
    else:
        query = query.order_by(Task.created_at.desc())

    pagination = query.paginate(page=page, per_page=20, error_out=False)
    tasks = pagination.items

    active_count = _apply_task_listing_filters(
        _build_task_visibility_query(show_finalized=False, include_relations=False),
        project_filter=project_filter,
        search_query=search_query,
    ).count()
    finalized_count = _apply_task_listing_filters(
        _build_task_visibility_query(show_finalized=True, include_relations=False),
        project_filter=project_filter,
        search_query=search_query,
    ).count()
    index_offset = (pagination.page - 1) * pagination.per_page
    page_total = pagination.pages if pagination.pages else 1
    page_info_text = f'Página {pagination.page} de {page_total}'
    start_index = index_offset + 1 if pagination.total else 0
    end_index = min(index_offset + len(tasks), pagination.total) if pagination.total else 0

    return render_template(
        'task_list.html',
        tasks=tasks,
        pagination=pagination,
        projects=_get_projects_for_task_filter(),
        project_filter=project_filter,
        search_query=search_query,
        show_finalized=show_finalized,
        list_endpoint='main.list_tasks_finalized' if show_finalized else 'main.list_tasks',
        index_offset=index_offset,
        page_info_text=page_info_text,
        start_index=start_index,
        end_index=end_index,
        active_count=active_count,
        finalized_count=finalized_count,
    )


@main_bp.route('/tarefas', methods=['GET'])
@login_required
def list_tasks():
    """Hub de itens de tarefas ativas, agrupado por projeto."""
    return _render_task_hub()


@main_bp.route('/tarefas/finalizadas', methods=['GET'])
@login_required
def list_tasks_finalized():
    """Lista tarefas finalizadas do usuário com filtros e paginação."""
    return _render_tasks_listing(show_finalized=True)


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
    can_view = _can_view_task(g.user, task)
    
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
    can_edit = _can_view_task(g.user, task)
    
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
    old_titulo = task.titulo
    old_project_id = task.project_id
    task.titulo = titulo
    task.project_id = project_id
    
    try:
        if old_titulo != task.titulo or old_project_id != task.project_id:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_updated',
                title=f'Tarefa atualizada: "{task.titulo}"',
                message=f'{g.user.name} atualizou os dados da tarefa.',
            )
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
    can_delete = _can_view_task(g.user, task)
    
    if not can_delete:
        flash('Você não tem permissão para excluir esta tarefa.', 'danger')
        return _redirect_back_or('main.list_tasks')
    
    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_deleted',
            title=f'Tarefa excluida: "{task.titulo}"',
            message=f'{g.user.name} excluiu a tarefa.',
            target_url=url_for('main.list_tasks'),
        )
        db.session.delete(task)
        db.session.commit()
        flash('Tarefa excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir tarefa: {str(e)}', 'danger')

    return _redirect_back_or('main.list_tasks_finalized' if task.is_finalized else 'main.list_tasks')


@main_bp.route('/tarefas/<int:task_id>/finalizar', methods=['POST'])
@login_required
def finalize_task(task_id):
    """Marca tarefa como finalizada."""
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(g.user, task):
        flash('Você não tem permissão para finalizar esta tarefa.', 'danger')
        return _redirect_back_or('main.list_tasks')

    if task.is_finalized:
        flash('Esta tarefa já está finalizada.', 'info')
        return _redirect_back_or('main.list_tasks_finalized')

    try:
        task.is_finalized = True
        task.finalized_at = datetime.datetime.utcnow()
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_finalized',
            title=f'Tarefa finalizada: "{task.titulo}"',
            message=f'{g.user.name} finalizou a tarefa.',
            target_url=url_for('main.list_tasks_finalized'),
        )
        db.session.commit()
        flash('Tarefa finalizada com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao finalizar tarefa: {str(e)}', 'danger')

    return _redirect_back_or('main.list_tasks_finalized')


@main_bp.route('/tarefas/<int:task_id>/reativar', methods=['POST'])
@login_required
def reactivate_task(task_id):
    """Reativa tarefa finalizada."""
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(g.user, task):
        flash('Você não tem permissão para reativar esta tarefa.', 'danger')
        return _redirect_back_or('main.list_tasks')

    if not task.is_finalized:
        flash('Esta tarefa já está ativa.', 'info')
        return _redirect_back_or('main.list_tasks')

    try:
        task.is_finalized = False
        task.finalized_at = None
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_reactivated',
            title=f'Tarefa reativada: "{task.titulo}"',
            message=f'{g.user.name} reativou a tarefa.',
        )
        db.session.commit()
        flash('Tarefa reativada com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao reativar tarefa: {str(e)}', 'danger')

    return _redirect_back_or('main.list_tasks')


def _can_access_project_in_tasks(project):
    if project is None:
        return True
    if g.user.is_admin:
        return True
    return g.user.has_access_to_area(project.area_responsavel)


def _resolve_hub_project_token(raw_project_value):
    project_value = (raw_project_value or '').strip()
    if not project_value:
        return None, 'Projeto é obrigatório.', 400

    if project_value == 'sem_projeto':
        return None, None, 200

    try:
        project_id = int(project_value)
    except (TypeError, ValueError):
        return None, 'Projeto inválido.', 400

    project = Project.query.get(project_id)
    if not project:
        return None, 'Projeto não encontrado.', 404

    if not _can_access_project_in_tasks(project):
        return None, 'Sem permissão para este projeto.', 403

    return project, None, 200


def _resolve_anchor_task_for_hub(project):
    """
    Resolve tarefa âncora de criação global:
    - projeto: tarefa ativa mais antiga; cria âncora se não existir;
    - sem_projeto: tarefa ativa avulsa do usuário; cria avulsa se não existir.
    """
    if project is None:
        anchor = (
            Task.query
            .filter(
                Task.project_id.is_(None),
                Task.created_by_id == g.user.id,
                Task.is_finalized.is_(False),
            )
            .order_by(Task.created_at.asc(), Task.id.asc())
            .first()
        )
        if anchor:
            return anchor

        anchor = Task(
            titulo='Tarefa avulsa',
            project_id=None,
            created_by_id=g.user.id,
        )
        db.session.add(anchor)
        db.session.flush()
        return anchor

    anchor = (
        Task.query
        .filter(
            Task.project_id == project.id,
            Task.is_finalized.is_(False),
        )
        .order_by(Task.created_at.asc(), Task.id.asc())
        .first()
    )
    if anchor:
        return anchor

    anchor = Task(
        titulo=f'Tarefa âncora - {project.titulo}',
        project_id=project.id,
        created_by_id=g.user.id,
    )
    db.session.add(anchor)
    db.session.flush()
    return anchor


def _get_assignable_users_for_hub_project(project):
    """Sugestões de responsável para contexto global por projeto."""
    candidate_ids = set()

    candidate_ids.add(g.user.id)
    admin_ids = [user_id for (user_id,) in User.query.with_entities(User.id).filter(User.is_admin.is_(True)).all()]
    candidate_ids.update(admin_ids)

    if project is not None and project.area_responsavel:
        area = project.area_responsavel
        area_user_ids = [
            user_id
            for (user_id,) in UserArea.query.with_entities(UserArea.user_id).filter_by(area=area).all()
        ]
        candidate_ids.update(area_user_ids)

        legacy_area_ids = [
            user_id
            for (user_id,) in User.query.with_entities(User.id).filter(User.area_responsavel == area).all()
        ]
        candidate_ids.update(legacy_area_ids)

    if not candidate_ids:
        return []

    return User.query.filter(User.id.in_(candidate_ids)).order_by(User.name.asc()).all()


@main_bp.route('/tarefas/itens/add', methods=['POST'])
@login_required
def add_task_item_global():
    """Cria item no hub global por projeto (ou sem_projeto)."""
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )

    project_raw = request.form.get('project')
    if project_raw is None:
        payload = request.get_json(silent=True) or {}
        project_raw = payload.get('project')

    project, project_error, status_code = _resolve_hub_project_token(project_raw)
    if project_error:
        if is_ajax:
            return jsonify({'success': False, 'message': project_error}), status_code
        flash(project_error, 'danger')
        return redirect(url_for('main.list_tasks'))

    descricao = (request.form.get('descricao') or '').strip()
    status = (request.form.get('status') or 'programado').strip()
    responsavel = (request.form.get('responsavel') or '').strip()
    prioridade = (request.form.get('prioridade') or '').strip() or None
    tipo_pedido = (request.form.get('tipo_pedido') or '').strip() or None

    if status not in VALID_STATUSES:
        status = 'programado'
    if prioridade and prioridade not in VALID_PRIORIDADES:
        prioridade = None
    if tipo_pedido and tipo_pedido not in VALID_TIPOS:
        tipo_pedido = None

    if not descricao:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Descrição é obrigatória.'}), 400
        flash('Descrição é obrigatória.', 'danger')
        return redirect(url_for('main.list_tasks'))

    try:
        anchor_task = _resolve_anchor_task_for_hub(project)
        is_valid_responsavel, canonical_responsavel, invalid_names = _validate_task_item_responsavel(
            anchor_task,
            responsavel,
        )
        if not is_valid_responsavel:
            message = _format_invalid_responsavel_message(invalid_names)
            if is_ajax:
                return jsonify({'success': False, 'message': message}), 400
            flash(message, 'danger')
            return redirect(url_for('main.list_tasks'))

        max_ordem = db.session.query(db.func.max(TaskItem.ordem)).filter_by(task_id=anchor_task.id).scalar() or 0
        item = TaskItem(
            descricao=descricao,
            status=status,
            responsavel=canonical_responsavel if canonical_responsavel else None,
            prioridade=prioridade,
            tipo_pedido=tipo_pedido,
            task_id=anchor_task.id,
            ordem=max_ordem + 1,
        )

        db.session.add(item)
        db.session.flush()
        notify_task_event(
            anchor_task,
            actor_user_id=g.user.id,
            event_type='task_item_created',
            title=f'Novo item em "{anchor_task.titulo}"',
            message=(
                f'{g.user.name} criou o item "{_preview_text(item.descricao, 90)}" '
                f'com status {_task_item_status_label(item.status)}.'
            ),
            item_id=item.id,
        )
        if item.responsavel:
            notify_task_assignment_change(
                anchor_task,
                item,
                g.user.id,
                old_responsavel=None,
                new_responsavel=item.responsavel,
            )
        db.session.commit()

        if is_ajax:
            return jsonify({
                'success': True,
                'item': {
                    'id': item.id,
                    'descricao': item.descricao,
                    'status': item.status,
                    'responsavel': item.responsavel or '',
                    'prioridade': item.prioridade or '',
                    'tipo_pedido': item.tipo_pedido or '',
                    'task_id': anchor_task.id,
                    'task_titulo': anchor_task.titulo,
                    'project_id': anchor_task.project_id,
                    'project_titulo': anchor_task.project.titulo if anchor_task.project else 'Sem projeto',
                    'project_value': str(anchor_task.project_id) if anchor_task.project_id else 'sem_projeto',
                    'comments_count': 0,
                    'anexos_count': 0,
                },
            })
        flash('Item adicionado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao adicionar item: {str(e)}', 'danger')

    return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas/sugestoes-responsavel', methods=['GET'])
@login_required
def get_hub_assignable_users():
    """API: usuários elegíveis por contexto do projeto no hub global."""
    project_raw = (request.args.get('project') or '').strip()
    project, project_error, status_code = _resolve_hub_project_token(project_raw)
    if project_error:
        return jsonify({'success': False, 'message': project_error}), status_code

    users = _get_assignable_users_for_hub_project(project)
    payload = [{'id': user.id, 'name': user.name} for user in users]

    q = (request.args.get('q') or '').strip().lower()
    if q:
        payload = [user for user in payload if q in (user['name'] or '').lower()]

    return jsonify({'users': payload})


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
    can_edit = _can_view_task(g.user, task)
    
    if not can_edit:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para adicionar itens.'}), 403
        flash('Você não tem permissão para adicionar itens a esta tarefa.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    descricao = request.form.get('descricao', '').strip()
    status = request.form.get('status', 'programado')
    responsavel = request.form.get('responsavel', '').strip()
    prioridade = request.form.get('prioridade', '').strip() or None
    tipo_pedido = request.form.get('tipo_pedido', '').strip() or None

    if prioridade not in VALID_PRIORIDADES:
        prioridade = None
    if tipo_pedido not in VALID_TIPOS:
        tipo_pedido = None

    # Validações
    if not descricao:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Descrição é obrigatória.'}), 400
        flash('Descrição é obrigatória.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))

    is_valid_responsavel, canonical_responsavel, invalid_names = _validate_task_item_responsavel(task, responsavel)
    if not is_valid_responsavel:
        message = _format_invalid_responsavel_message(invalid_names)
        if is_ajax:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))

    # Calcular ordem
    max_ordem = db.session.query(db.func.max(TaskItem.ordem)).filter_by(task_id=task_id).scalar() or 0

    # Criar item
    item = TaskItem(
        descricao=descricao,
        status=status,
        responsavel=canonical_responsavel if canonical_responsavel else None,
        prioridade=prioridade,
        tipo_pedido=tipo_pedido,
        task_id=task_id,
        ordem=max_ordem + 1
    )

    try:
        db.session.add(item)
        db.session.flush()
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_item_created',
            title=f'Novo item em "{task.titulo}"',
            message=f'{g.user.name} criou o item "{_preview_text(item.descricao, 90)}" com status {_task_item_status_label(item.status)}.',
            item_id=item.id,
        )
        if item.responsavel:
            notify_task_assignment_change(task, item, g.user.id, old_responsavel=None, new_responsavel=item.responsavel)
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'item': {
                    'id': item.id,
                    'descricao': item.descricao,
                    'status': item.status,
                    'responsavel': item.responsavel or '',
                    'prioridade': item.prioridade or '',
                    'tipo_pedido': item.tipo_pedido or '',
                    'comments_count': 0,
                    'anexos_count': 0,
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
    can_edit = _can_view_task(g.user, task)
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    descricao = request.form.get('descricao', item.descricao).strip()
    status = request.form.get('status', item.status)

    if 'responsavel' in request.form:
        responsavel = request.form.get('responsavel', '').strip()
    else:
        responsavel = item.responsavel or ''

    if 'prioridade' in request.form:
        prioridade = request.form.get('prioridade', '').strip() or None
        if prioridade and prioridade not in VALID_PRIORIDADES:
            prioridade = None
    else:
        prioridade = item.prioridade

    if 'tipo_pedido' in request.form:
        incoming_tipo_pedido = request.form.get('tipo_pedido', '').strip() or None
        if incoming_tipo_pedido is None:
            tipo_pedido = None
        elif incoming_tipo_pedido in VALID_TIPOS:
            tipo_pedido = incoming_tipo_pedido
        elif incoming_tipo_pedido in LEGACY_TIPOS and item.tipo_pedido in LEGACY_TIPOS:
            # Compatibilidade: preserva legado quando o valor semântico não muda.
            tipo_pedido = item.tipo_pedido
        else:
            tipo_pedido = None
    else:
        tipo_pedido = item.tipo_pedido

    # Validações
    if not descricao:
        return jsonify({'success': False, 'message': 'Descrição é obrigatória'}), 400

    is_valid_responsavel, resolved_responsavel, invalid_names = _resolve_responsavel_for_item_edit(item, responsavel)
    if not is_valid_responsavel:
        return jsonify({'success': False, 'message': _format_invalid_responsavel_message(invalid_names)}), 400

    old_descricao = item.descricao
    old_status = item.status
    old_responsavel = item.responsavel
    old_prioridade = item.prioridade
    old_tipo_pedido = item.tipo_pedido

    # Atualizar item
    item.descricao = descricao
    item.status = status
    item.responsavel = resolved_responsavel if resolved_responsavel else None
    item.prioridade = prioridade
    item.tipo_pedido = tipo_pedido

    try:
        changes = []
        if old_descricao != item.descricao:
            changes.append('descricao')
        if old_status != item.status:
            changes.append(f'status para {_task_item_status_label(item.status)}')
        if old_prioridade != item.prioridade:
            changes.append(f'prioridade para "{item.prioridade or "vazio"}"')
        if old_tipo_pedido != item.tipo_pedido:
            changes.append(f'tipo para "{item.tipo_pedido or "vazio"}"')

        if changes:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_item_updated',
                title=f'Item atualizado em "{task.titulo}"',
                message=f'{g.user.name} atualizou o item "{_preview_text(item.descricao, 90)}": {", ".join(changes)}.',
                item_id=item.id,
            )

        if (old_responsavel or '') != (item.responsavel or ''):
            notify_task_assignment_change(
                task,
                item,
                g.user.id,
                old_responsavel=old_responsavel,
                new_responsavel=item.responsavel,
            )

        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Item atualizado',
            'item': {
                'id': item.id,
                'descricao': item.descricao,
                'status': item.status,
                'responsavel': item.responsavel or '',
                'prioridade': item.prioridade or '',
                'tipo_pedido': item.tipo_pedido or '',
                'anexos_count': len(item.anexos),
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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    # Verificar permissão
    can_delete = _can_view_task(g.user, task)
    
    if not can_delete:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para excluir este item.', 'item_id': item_id}), 403
        flash('Você não tem permissão para excluir este item.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_item_deleted',
            title=f'Item excluido em "{task.titulo}"',
            message=f'{g.user.name} excluiu o item "{_preview_text(item.descricao, 90)}".',
            item_id=item.id,
            target_url=url_for('main.task_detail', task_id=task.id),
        )
        db.session.delete(item)
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Item excluído com sucesso!', 'item_id': item_id})
        flash('Item excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e), 'item_id': item_id}), 500
        flash(f'Erro ao excluir item: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/tarefas/itens/<int:item_id>/update_status', methods=['POST'])
@login_required
def update_task_item_status(item_id):
    """Atualiza status do item via AJAX"""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    
    # Verificar permissão
    can_edit = _can_view_task(g.user, task)
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    status = request.json.get('status')
    if status not in ['programado', 'em_andamento', 'validacao', 'finalizado']:
        return jsonify({'success': False, 'message': 'Status inválido'}), 400
    
    old_status = item.status
    item.status = status
    
    try:
        if old_status != item.status:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_item_status_updated',
                title=f'Status atualizado em "{task.titulo}"',
                message=(
                    f'{g.user.name} alterou o status do item "{_preview_text(item.descricao, 90)}" '
                    f'de {_task_item_status_label(old_status)} para {_task_item_status_label(item.status)}.'
                ),
                item_id=item.id,
            )
        db.session.commit()
        return jsonify({'success': True, 'message': 'Status atualizado'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/itens/<int:item_id>/update_prioridade', methods=['POST'])
@login_required
def update_task_item_prioridade(item_id):
    """Atualiza prioridade do item via AJAX"""
    item = TaskItem.query.get_or_404(item_id)
    if not _can_view_task(g.user, item.task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    prioridade = request.json.get('prioridade', '') or None
    if prioridade and prioridade not in VALID_PRIORIDADES:
        return jsonify({'success': False, 'message': 'Prioridade inválida'}), 400
    old_prioridade = item.prioridade
    item.prioridade = prioridade
    try:
        if old_prioridade != item.prioridade:
            notify_task_event(
                item.task,
                actor_user_id=g.user.id,
                event_type='task_item_priority_updated',
                title=f'Prioridade atualizada em "{item.task.titulo}"',
                message=(
                    f'{g.user.name} alterou a prioridade do item "{_preview_text(item.descricao, 90)}" '
                    f'de "{old_prioridade or "vazio"}" para "{item.prioridade or "vazio"}".'
                ),
                item_id=item.id,
            )
        db.session.commit()
        return jsonify({'success': True, 'prioridade': item.prioridade or ''})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/itens/<int:item_id>/update_tipo', methods=['POST'])
@login_required
def update_task_item_tipo(item_id):
    """Atualiza tipo_pedido do item via AJAX"""
    item = TaskItem.query.get_or_404(item_id)
    if not _can_view_task(g.user, item.task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    tipo = request.json.get('tipo_pedido', '') or None
    if tipo and tipo not in VALID_TIPOS:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400
    old_tipo = item.tipo_pedido
    item.tipo_pedido = tipo
    try:
        if old_tipo != item.tipo_pedido:
            notify_task_event(
                item.task,
                actor_user_id=g.user.id,
                event_type='task_item_type_updated',
                title=f'Tipo atualizado em "{item.task.titulo}"',
                message=(
                    f'{g.user.name} alterou o tipo do item "{_preview_text(item.descricao, 90)}" '
                    f'de "{old_tipo or "vazio"}" para "{item.tipo_pedido or "vazio"}".'
                ),
                item_id=item.id,
            )
        db.session.commit()
        return jsonify({'success': True, 'tipo_pedido': item.tipo_pedido or ''})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/itens/reordenar', methods=['POST'])
@login_required
def reorder_task_items(task_id):
    """Reordena itens da tarefa"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar permissão
    can_edit = _can_view_task(g.user, task)
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    try:
        payload = request.get_json(silent=True) or {}
        ordem_items_raw = payload.get('ordem', [])
        if not isinstance(ordem_items_raw, list):
            ordem_items_raw = []

        # Sanitiza entrada: ignora inválidos e ids duplicados preservando ordem
        ordem_items = []
        seen_ids = set()
        for raw_id in ordem_items_raw:
            try:
                item_id = int(raw_id)
            except (TypeError, ValueError):
                continue

            if item_id in seen_ids:
                continue

            seen_ids.add(item_id)
            ordem_items.append(item_id)

        task_items = TaskItem.query.filter_by(task_id=task_id).order_by(TaskItem.ordem.asc(), TaskItem.id.asc()).all()
        task_items_by_id = {item.id: item for item in task_items}

        ordered_items = [task_items_by_id[item_id] for item_id in ordem_items if item_id in task_items_by_id]
        ordered_item_ids = {item.id for item in ordered_items}
        remaining_items = [item for item in task_items if item.id not in ordered_item_ids]
        final_order = ordered_items + remaining_items

        for index, item in enumerate(final_order, start=1):
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
    return _can_view_task(g.user, task)


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
        db.session.flush()
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_item_comment_added',
            title=f'Novo comentario em "{task.titulo}"',
            message=f'{g.user.name} comentou: "{_preview_text(comment.content, 120)}".',
            item_id=item.id,
        )
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
    
    old_content = comment.content
    comment.content = content
    comment.updated_at = datetime.datetime.utcnow()
    try:
        notify_task_event(
            comment.task_item.task,
            actor_user_id=g.user.id,
            event_type='task_item_comment_updated',
            title=f'Comentario editado em "{comment.task_item.task.titulo}"',
            message=(
                f'{g.user.name} editou um comentario no item "{_preview_text(comment.task_item.descricao, 90)}": '
                f'"{_preview_text(old_content, 70)}" -> "{_preview_text(comment.content, 70)}".'
            ),
            item_id=comment.task_item_id,
        )
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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    if comment.user_id != g.user.id:
        message = 'Você só pode excluir seus próprios comentários.'
        if is_ajax:
            return jsonify({'success': False, 'message': message, 'comment_id': comment_id}), 403
        flash(message, 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    try:
        notify_task_event(
            comment.task_item.task,
            actor_user_id=g.user.id,
            event_type='task_item_comment_deleted',
            title=f'Comentario removido em "{comment.task_item.task.titulo}"',
            message=(
                f'{g.user.name} removeu um comentario no item '
                f'"{_preview_text(comment.task_item.descricao, 90)}".'
            ),
            item_id=comment.task_item_id,
        )
        db.session.delete(comment)
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Comentário excluído.', 'comment_id': comment_id})
        flash('Comentário excluído.', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e), 'comment_id': comment_id}), 500
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
    
    # Buscar apenas tarefas ativas do projeto (escopo global de arquivamento)
    tasks = (
        Task.query
        .options(joinedload(Task.items), joinedload(Task.created_by))
        .filter_by(project_id=project_id, is_finalized=False)
        .order_by(Task.created_at.desc())
        .all()
    )

    finalized_count = (
        Task.query
        .filter_by(project_id=project_id, is_finalized=True)
        .count()
    )

    finalized_tasks_url = url_for('main.list_tasks_finalized', project=project_id)
    
    return render_template(
        'project_tasks.html',
        project=project,
        tasks=tasks,
        finalized_count=finalized_count,
        finalized_tasks_url=finalized_tasks_url,
    )

# ===================================
# ANEXOS DE ITENS DE TAREFA
# ===================================

@main_bp.route('/tarefas/itens/<int:item_id>/anexos', methods=['GET'])
@login_required
def list_task_item_anexos(item_id):
    """Lista anexos de um item (retorna JSON)."""
    item = TaskItem.query.get_or_404(item_id)
    if not _can_view_task(g.user, item.task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    return jsonify({
        'success': True,
        'anexos': [
            {
                'id': a.id,
                'filename': a.filename,
                'content_type': a.content_type or '',
                'uploaded_by': a.uploaded_by.name,
                'created_at': format_local_time(a.created_at),
                'is_image': (a.content_type or '').startswith('image/'),
                'url': url_for('main.view_task_item_anexo', anexo_id=a.id),
            }
            for a in item.anexos
        ],
        'count': len(item.anexos),
    })


@main_bp.route('/tarefas/itens/<int:item_id>/anexos/add', methods=['POST'])
@login_required
def add_task_item_anexo(item_id):
    """Faz upload de um anexo para o item."""
    item = TaskItem.query.get_or_404(item_id)
    if not _can_view_task(g.user, item.task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo enviado.'}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'Arquivo inválido.'}), 400

    if not _allowed_attachment(file.filename):
        return jsonify({'success': False, 'message': 'Tipo de arquivo não permitido.'}), 400

    original_name = file.filename[:255]
    safe_name = secure_filename(file.filename)
    ext = safe_name.rsplit('.', 1)[1].lower() if '.' in safe_name else ''
    stored_name = str(uuid.uuid4()) + ('.' + ext if ext else '')
    content_type = file.content_type or 'application/octet-stream'

    upload_folder = _get_upload_folder()
    file_path = os.path.join(upload_folder, stored_name)

    try:
        file.save(file_path)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao salvar arquivo: {str(e)}'}), 500

    anexo = TaskItemAnexo(
        task_item_id=item_id,
        filename=original_name,
        stored_filename=stored_name,
        content_type=content_type,
        uploaded_by_id=g.user.id,
    )
    try:
        db.session.add(anexo)
        db.session.flush()
        notify_task_event(
            item.task,
            actor_user_id=g.user.id,
            event_type='task_item_attachment_added',
            title=f'Novo anexo em "{item.task.titulo}"',
            message=f'{g.user.name} anexou "{_preview_text(anexo.filename, 90)}" ao item "{_preview_text(item.descricao, 90)}".',
            item_id=item.id,
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'anexo': {
                'id': anexo.id,
                'filename': anexo.filename,
                'content_type': content_type,
                'uploaded_by': g.user.name,
                'created_at': format_local_time(anexo.created_at),
                'is_image': content_type.startswith('image/'),
                'url': url_for('main.view_task_item_anexo', anexo_id=anexo.id),
            },
            'anexos_count': len(item.anexos),
        })
    except Exception as e:
        db.session.rollback()
        try:
            os.remove(file_path)
        except OSError:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/anexos/<int:anexo_id>', methods=['GET'])
@login_required
def view_task_item_anexo(anexo_id):
    """Serve o arquivo de um anexo."""
    anexo = TaskItemAnexo.query.get_or_404(anexo_id)
    if not _can_view_task(g.user, anexo.task_item.task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    upload_folder = _get_upload_folder()
    file_path = os.path.join(upload_folder, anexo.stored_filename)

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'Arquivo não encontrado.'}), 404

    return send_file(file_path, download_name=anexo.filename, as_attachment=False)


@main_bp.route('/tarefas/anexos/<int:anexo_id>/delete', methods=['POST'])
@login_required
def delete_task_item_anexo(anexo_id):
    """Exclui um anexo."""
    anexo = TaskItemAnexo.query.get_or_404(anexo_id)
    item = anexo.task_item
    if not _can_view_task(g.user, item.task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    upload_folder = _get_upload_folder()
    file_path = os.path.join(upload_folder, anexo.stored_filename)

    try:
        notify_task_event(
            item.task,
            actor_user_id=g.user.id,
            event_type='task_item_attachment_deleted',
            title=f'Anexo removido em "{item.task.titulo}"',
            message=f'{g.user.name} removeu o anexo "{_preview_text(anexo.filename, 90)}" do item "{_preview_text(item.descricao, 90)}".',
            item_id=item.id,
        )
        db.session.delete(anexo)
        db.session.commit()
        try:
            os.remove(file_path)
        except OSError:
            pass
        return jsonify({
            'success': True,
            'message': 'Anexo excluído.',
            'anexos_count': len(item.anexos),
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/sugestoes-responsavel', methods=['GET'])
@login_required
def get_task_assignable_users(task_id):
    """API: usuários elegíveis para responsável conforme regra de visualização da tarefa."""
    task = Task.query.get_or_404(task_id)

    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    assignable_users = _get_task_assignable_users(task)
    users = [{'id': u.id, 'name': u.name} for u in assignable_users]

    q = (request.args.get('q') or '').strip().lower()
    if q:
        users = [u for u in users if q in (u['name'] or '').lower()]

    return jsonify({'users': users})
