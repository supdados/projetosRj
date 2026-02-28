import datetime
import os
import re
import uuid
from urllib.parse import urlencode, urlparse

from flask import flash, g, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from models import (
    LegacyTaskRedirect,
    Project,
    Task,
    TaskAnexo,
    TaskComment,
    User,
    UserArea,
    db,
)
from services.notifications import notify_task_assignment_change, notify_task_event
from time_utils import utc_now

from .blueprint import main_bp
from .decorators import login_required
from .shared import format_local_time

VALID_PRIORIDADES = {'baixa', 'media', 'alta', 'urgente'}
VALID_TIPOS = {'bug', 'melhoria', 'duvida', 'outros'}
LEGACY_TIPOS = {'implementacao'}
VALID_STATUSES = {'programado', 'em_andamento', 'validacao', 'finalizado'}
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}
TASK_PRIORIDADE_ORDER = ('baixa', 'media', 'alta', 'urgente')
TASK_TIPO_ORDER = ('bug', 'melhoria', 'duvida', 'outros', 'implementacao')
TASK_STATUS_ORDER = ('programado', 'em_andamento', 'validacao', 'finalizado')


def _get_upload_folder():
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    folder = os.path.join(basedir, 'instance', 'uploads', 'tasks')
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _task_status_label(status):
    labels = {
        'programado': 'Programado',
        'em_andamento': 'Em andamento',
        'validacao': 'Validação',
        'finalizado': 'Finalizado',
    }
    return labels.get(status, status or '')


def _task_prioridade_label(prioridade):
    labels = {
        'baixa': 'Baixa',
        'media': 'Média',
        'alta': 'Alta',
        'urgente': 'Urgente',
    }
    return labels.get(prioridade, prioridade or '')


def _task_tipo_label(tipo):
    labels = {
        'bug': 'Bug',
        'melhoria': 'Melhoria',
        'duvida': 'Dúvida',
        'outros': 'Outros',
        'implementacao': 'Implementação (legado)',
    }
    return labels.get(tipo, tipo or '')


def _preview_text(value, max_length=90):
    text_value = ' '.join((value or '').split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + '...'


def _normalize_person_name(name):
    return ' '.join((name or '').strip().split())


def _split_responsavel_names(raw_value):
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
    return ', '.join(_split_responsavel_names(raw_value))


def _read_task_filter_values(source):
    return {
        'selected_area': (source.get('area') or '').strip(),
        'project_filter': (source.get('project') or '').strip(),
        'prioridade_filter': (source.get('prioridade') or '').strip(),
        'tipo_filter': (source.get('tipo') or '').strip(),
        'status_filter': (source.get('status') or '').strip(),
        'responsavel_filter': _normalize_person_name(source.get('responsavel') or ''),
    }


def _merge_task_filter_values(*values_list):
    merged = {
        'selected_area': '',
        'project_filter': '',
        'prioridade_filter': '',
        'tipo_filter': '',
        'status_filter': '',
        'responsavel_filter': '',
    }

    for values in values_list:
        if not values:
            continue
        for key in merged:
            value = values.get(key)
            if value:
                merged[key] = value

    return merged


def _ordered_task_filter_values(values, preferred_order):
    present = {value for value in values if value}
    ordered = [value for value in preferred_order if value in present]
    ordered.extend(sorted((value for value in present if value not in preferred_order), key=lambda item: item.casefold()))
    return ordered


def _ensure_filter_option(options, selected_value, label):
    if not selected_value:
        return
    if any(option['value'] == selected_value for option in options):
        return
    options.append({'value': selected_value, 'label': label})


def _build_task_filter_options(tasks, selected_filters=None):
    selected_filters = selected_filters or {}

    prioridade_options = [
        {'value': value, 'label': _task_prioridade_label(value)}
        for value in _ordered_task_filter_values(
            [task.prioridade for task in tasks if task.prioridade],
            TASK_PRIORIDADE_ORDER,
        )
    ]
    tipo_options = [
        {'value': value, 'label': _task_tipo_label(value)}
        for value in _ordered_task_filter_values(
            [task.tipo_pedido for task in tasks if task.tipo_pedido],
            TASK_TIPO_ORDER,
        )
    ]
    status_options = [
        {'value': value, 'label': _task_status_label(value)}
        for value in _ordered_task_filter_values(
            [task.status for task in tasks if task.status],
            TASK_STATUS_ORDER,
        )
    ]

    responsavel_values = []
    for task in tasks:
        responsavel_values.extend(_split_responsavel_names(task.responsavel or ''))
    responsavel_options = [
        {'value': value, 'label': value}
        for value in sorted(set(responsavel_values), key=lambda item: item.casefold())
    ]

    _ensure_filter_option(
        prioridade_options,
        selected_filters.get('prioridade_filter', ''),
        _task_prioridade_label(selected_filters.get('prioridade_filter', '')),
    )
    _ensure_filter_option(
        tipo_options,
        selected_filters.get('tipo_filter', ''),
        _task_tipo_label(selected_filters.get('tipo_filter', '')),
    )
    _ensure_filter_option(
        status_options,
        selected_filters.get('status_filter', ''),
        _task_status_label(selected_filters.get('status_filter', '')),
    )
    _ensure_filter_option(
        responsavel_options,
        selected_filters.get('responsavel_filter', ''),
        selected_filters.get('responsavel_filter', ''),
    )

    return {
        'prioridade_options': prioridade_options,
        'tipo_options': tipo_options,
        'status_options': status_options,
        'responsavel_options': responsavel_options,
    }


def _build_task_listing_url(
    endpoint,
    *,
    selected_area='',
    project_filter='',
    prioridade_filter='',
    tipo_filter='',
    status_filter='',
    responsavel_filter='',
    page=None,
    project_id=None,
):
    kwargs = {}
    if project_id is not None:
        kwargs['project_id'] = project_id
    if selected_area:
        kwargs['area'] = selected_area
    if project_filter:
        kwargs['project'] = project_filter
    if prioridade_filter:
        kwargs['prioridade'] = prioridade_filter
    if tipo_filter:
        kwargs['tipo'] = tipo_filter
    if status_filter:
        kwargs['status'] = status_filter
    if responsavel_filter:
        kwargs['responsavel'] = responsavel_filter
    if page is not None:
        kwargs['page'] = page
    return url_for(endpoint, **kwargs)


def _build_legacy_query_args():
    query_args = request.args.to_dict(flat=True)
    if query_args:
        return '?' + urlencode(query_args)
    return ''


def _task_active_target_url(task):
    if task and task.project_id:
        return url_for('main.project_tasks', project_id=task.project_id, focus_task=task.id)
    if task:
        return url_for('main.list_tasks', focus_task=task.id)
    return url_for('main.list_tasks')


def _format_invalid_responsavel_message(invalid_names):
    invalid_str = ', '.join(invalid_names)
    return f'Responsável inválido: {invalid_str}. Selecione somente usuários com permissão de visualização.'


def _can_view_task(user, task):
    return (
        user.is_admin
        or (task.project_id is None and task.created_by_id == user.id)
        or (task.project_id and task.project and task.project.area_responsavel in user.get_areas())
    )


def _can_access_project_in_tasks(project):
    if project is None:
        return True
    if g.user.is_admin:
        return True
    return g.user.has_access_to_area(project.area_responsavel)


def _resolve_project_token(raw_project_value, allow_empty=False):
    project_value = (raw_project_value or '').strip()
    if not project_value:
        if allow_empty:
            return None, None, 200
        return None, 'Projeto é obrigatório.', 400

    if project_value == 'sem_projeto':
        return None, None, 200

    try:
        project_id = int(project_value)
    except (TypeError, ValueError):
        return None, 'Projeto inválido.', 400

    project = db.session.get(Project, project_id)
    if not project:
        return None, 'Projeto não encontrado.', 404

    if not _can_access_project_in_tasks(project):
        return None, 'Sem permissão para este projeto.', 403

    return project, None, 200


def _get_assignable_users_for_area(area):
    candidate_ids = {g.user.id}

    admin_ids = [user_id for (user_id,) in User.query.with_entities(User.id).filter(User.is_admin.is_(True)).all()]
    candidate_ids.update(admin_ids)

    if area:
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


def _get_assignable_users_for_project(project):
    area = project.area_responsavel if project is not None else None
    return _get_assignable_users_for_area(area)


def _validate_task_responsavel(project, raw_value):
    parsed_names = _split_responsavel_names(raw_value)
    if not parsed_names:
        return True, '', []

    allowed_users = _get_assignable_users_for_project(project)
    allowed_by_key = {}
    for user in allowed_users:
        canonical = _normalize_person_name(user.name)
        if canonical:
            allowed_by_key[canonical.casefold()] = canonical

    canonical_names = []
    invalid_names = []
    seen = set()

    for name in parsed_names:
        canonical = allowed_by_key.get(name.casefold())
        if not canonical:
            invalid_names.append(name)
            continue
        key = canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        canonical_names.append(canonical)

    return len(invalid_names) == 0, ', '.join(canonical_names), invalid_names


def _resolve_responsavel_for_edit(task, incoming_raw_value, project):
    current_normalized = _normalize_responsavel_value(task.responsavel or '')
    incoming_normalized = _normalize_responsavel_value(incoming_raw_value)
    if incoming_normalized == current_normalized:
        return True, (task.responsavel or ''), []
    return _validate_task_responsavel(project, incoming_raw_value)


def _serialize_task_payload(task):
    project = task.project
    project_id = project.id if project else None
    return {
        'id': task.id,
        'descricao': task.descricao,
        'status': task.status,
        'responsavel': task.responsavel or '',
        'prioridade': task.prioridade or '',
        'tipo_pedido': task.tipo_pedido or '',
        'task_id': task.id,
        'task_titulo': task.descricao,
        'project_id': project_id,
        'project_titulo': project.titulo if project else 'Sem projeto',
        'project_value': str(project_id) if project_id else 'sem_projeto',
        'comments_count': len(task.comments),
        'anexos_count': len(task.anexos),
    }


def _resolve_task_hub_area_scope(selected_area):
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


def _build_visible_tasks_query(
    include_archived=False,
    selected_area='',
    project_filter='',
    prioridade_filter='',
    tipo_filter='',
    status_filter='',
    responsavel_filter='',
    include_relations=True,
):
    area_scope, normalized_area = _resolve_task_hub_area_scope(selected_area)

    query = Task.query
    if include_relations:
        query = query.options(
            joinedload(Task.project),
            joinedload(Task.comments).joinedload(TaskComment.author),
            joinedload(Task.anexos),
        )

    query = query.outerjoin(Project, Task.project_id == Project.id)

    if not g.user.is_admin:
        visibility_filters = [and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)]
        if area_scope:
            visibility_filters.insert(
                0,
                and_(Task.project_id.isnot(None), Project.area_responsavel.in_(area_scope)),
            )
        query = query.filter(or_(*visibility_filters))

    if normalized_area:
        query = query.filter(Task.project_id.isnot(None), Project.area_responsavel == normalized_area)

    if project_filter:
        if project_filter == 'sem_projeto':
            query = query.filter(Task.project_id.is_(None))
        else:
            try:
                project_id = int(project_filter)
            except (TypeError, ValueError):
                return query.filter(db.false())
            query = query.filter(Task.project_id == project_id)

    if prioridade_filter:
        query = query.filter(Task.prioridade == prioridade_filter)

    if tipo_filter:
        query = query.filter(Task.tipo_pedido == tipo_filter)

    if status_filter:
        query = query.filter(Task.status == status_filter)

    if responsavel_filter:
        escaped_responsavel = responsavel_filter.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = f"%{escaped_responsavel}%"
        query = query.filter(Task.responsavel.ilike(pattern, escape='\\'))

    query = query.filter(Task.is_archived.is_(bool(include_archived)))

    return query.order_by(
        Project.titulo.asc(),
        Task.ordem.asc(),
        Task.created_at.asc(),
        Task.id.asc(),
    )


def _group_hub_tasks_by_project(tasks):
    groups = {}

    for task in tasks:
        project = task.project
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
                'tasks': [],
                # Compatibilidade com template/JS legado.
                'items': [],
            }

        task.hub_project_value = project_value
        task.hub_project_titulo = project_title
        task.hub_task_titulo = task.descricao
        task.hub_task_id = task.id

        groups[group_key]['tasks'].append(task)
        groups[group_key]['items'].append(task)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            group['project_id'] is None,
            (group['project_titulo'] or '').casefold(),
        ),
    )

    return ordered_groups


def _build_task_hub_area_options(include_archived=False):
    base_query = (
        db.session.query(Project.area_responsavel)
        .join(Task, Task.project_id == Project.id)
        .filter(
            Task.is_archived.is_(bool(include_archived)),
            Project.area_responsavel.isnot(None),
        )
    )

    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if not user_areas:
            return []
        base_query = base_query.filter(Project.area_responsavel.in_(user_areas))

    rows = base_query.distinct().all()
    return sorted({(area or '').strip() for (area,) in rows if (area or '').strip()})


def _get_projects_for_task_filter(selected_area=''):
    query = Project.query
    if g.user.is_admin:
        if selected_area:
            query = query.filter(Project.area_responsavel == selected_area)
        return query.order_by(Project.titulo.asc()).all()

    user_areas = g.user.get_areas()
    if not user_areas:
        return []

    query = query.filter(Project.area_responsavel.in_(user_areas))
    if selected_area:
        if selected_area not in user_areas:
            return []
        query = query.filter(Project.area_responsavel == selected_area)

    return query.order_by(Project.titulo.asc()).all()


def _render_task_hub(locked_project=None, template_name='task_hub.html', include_archived=False):
    filter_values = _read_task_filter_values(request.args)
    selected_area = filter_values['selected_area']
    project_filter = filter_values['project_filter']
    prioridade_filter = filter_values['prioridade_filter']
    tipo_filter = filter_values['tipo_filter']
    status_filter = filter_values['status_filter']
    responsavel_filter = filter_values['responsavel_filter']

    if locked_project is not None:
        selected_area = ''
        project_filter = str(locked_project.id)

    tasks = _build_visible_tasks_query(
        include_archived=include_archived,
        selected_area=selected_area,
        project_filter=project_filter,
        prioridade_filter=prioridade_filter,
        tipo_filter=tipo_filter,
        status_filter=status_filter,
        responsavel_filter=responsavel_filter,
    ).all()
    groups = _group_hub_tasks_by_project(tasks)
    if locked_project is not None and not include_archived and not groups:
        groups = [
            {
                'key': f'project:{locked_project.id}',
                'project_id': locked_project.id,
                'project_value': str(locked_project.id),
                'project_titulo': locked_project.titulo,
                'project_area': locked_project.area_responsavel,
                'tasks': [],
                'items': [],
            }
        ]

    filter_scope_tasks = _build_visible_tasks_query(
        include_archived=include_archived,
        selected_area=selected_area,
        project_filter='',
    ).all()
    filter_scope_groups = _group_hub_tasks_by_project(filter_scope_tasks)

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
    if locked_project is not None and not selected_project_label:
        selected_project_label = locked_project.titulo

    attribute_scope_tasks = _build_visible_tasks_query(
        include_archived=include_archived,
        selected_area=selected_area,
        project_filter=project_filter,
        include_relations=False,
    ).all()
    filter_options = _build_task_filter_options(
        attribute_scope_tasks,
        selected_filters={
            'prioridade_filter': prioridade_filter,
            'tipo_filter': tipo_filter,
            'status_filter': status_filter,
            'responsavel_filter': responsavel_filter,
        },
    )

    user_areas = g.user.get_areas()
    show_area_selector = (locked_project is None) and (g.user.is_admin or len(user_areas) > 1)
    area_options = _build_task_hub_area_options(include_archived=include_archived) if show_area_selector else []
    filter_form_endpoint = 'main.project_tasks' if locked_project else ('main.list_tasks_archived' if include_archived else 'main.list_tasks')
    filter_form_action = _build_task_listing_url(
        filter_form_endpoint,
        project_id=locked_project.id if locked_project else None,
    )
    clear_url = _build_task_listing_url(
        filter_form_endpoint,
        project_id=locked_project.id if locked_project else None,
    )

    archived_url = None
    active_url = None
    active_count = None
    if include_archived:
        active_url = _build_task_listing_url(
            'main.list_tasks',
            selected_area=selected_area,
            project_filter=project_filter,
            prioridade_filter=prioridade_filter,
            tipo_filter=tipo_filter,
            status_filter=status_filter,
            responsavel_filter=responsavel_filter,
        )
        active_count = _build_visible_tasks_query(
            include_archived=False,
            selected_area=selected_area,
            project_filter=project_filter,
            prioridade_filter=prioridade_filter,
            tipo_filter=tipo_filter,
            status_filter=status_filter,
            responsavel_filter=responsavel_filter,
            include_relations=False,
        ).count()
    else:
        archived_url = _build_task_listing_url(
            'main.list_tasks_archived',
            selected_area=selected_area,
            project_filter=project_filter,
            prioridade_filter=prioridade_filter,
            tipo_filter=tipo_filter,
            status_filter=status_filter,
            responsavel_filter=responsavel_filter,
        )

    if include_archived:
        page_title = 'Tarefas arquivadas'
        page_subtitle = 'Itens retirados da visão ativa'
        section_title = 'Tarefas arquivadas'
        empty_title = 'Nenhuma tarefa arquivada'
        empty_text = 'Ajuste os filtros ou arquive tarefas na visão ativa.'
    elif locked_project:
        page_title = 'Tarefas'
        page_subtitle = 'Gerenciamento de tarefas'
        section_title = 'Tarefas ativas'
        empty_title = 'Nenhuma tarefa neste projeto'
        empty_text = 'Não há tarefas ativas visíveis neste projeto.'
    else:
        page_title = 'Tarefas'
        page_subtitle = 'Gerenciamento de tarefas'
        section_title = 'Tarefas ativas'
        empty_title = 'Nenhuma tarefa encontrada'
        empty_text = 'Ajuste os filtros para visualizar tarefas ativas.'

    return render_template(
        template_name,
        archived_mode=include_archived,
        groups=groups,
        project_options=project_options,
        selected_project=project_filter,
        selected_project_label=selected_project_label,
        selected_area=selected_area,
        area_options=area_options,
        selected_prioridade=prioridade_filter,
        selected_tipo=tipo_filter,
        selected_status=status_filter,
        selected_responsavel=responsavel_filter,
        prioridade_options=filter_options['prioridade_options'],
        tipo_options=filter_options['tipo_options'],
        status_options=filter_options['status_options'],
        responsavel_options=filter_options['responsavel_options'],
        show_area_selector=show_area_selector,
        total_items=len(tasks),
        project_locked=bool(locked_project),
        project_locked_obj=locked_project,
        page_title=page_title,
        page_subtitle=page_subtitle,
        section_title=section_title,
        empty_title=empty_title,
        empty_text=empty_text,
        filter_form_action=filter_form_action,
        clear_url=clear_url,
        archived_url=archived_url,
        active_url=active_url,
        active_count=active_count,
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

    if not parsed.netloc and parsed.path.startswith('/'):
        target = parsed.path
        if parsed.query:
            target = f'{target}?{parsed.query}'
        return target

    if parsed.netloc and parsed.netloc == request.host:
        target = parsed.path or '/'
        if parsed.query:
            target = f'{target}?{parsed.query}'
        return target

    return None


def _redirect_back_or(default_endpoint, **kwargs):
    next_url = _get_safe_next_url()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **kwargs))


def _extract_creation_payload(default_project=None):
    payload = request.get_json(silent=True) or {}

    project_raw = request.form.get('project')
    if project_raw is None:
        project_raw = request.form.get('project_id')
    if project_raw is None:
        project_raw = payload.get('project')
    if project_raw is None:
        project_raw = payload.get('project_id')

    if project_raw is None and default_project is not None:
        project_raw = str(default_project.id)

    descricao = (request.form.get('descricao') or payload.get('descricao') or '').strip()
    if not descricao:
        descricao = (request.form.get('titulo') or payload.get('titulo') or '').strip()

    status = (request.form.get('status') or payload.get('status') or 'programado').strip()
    responsavel = (request.form.get('responsavel') or payload.get('responsavel') or '').strip()
    prioridade = (request.form.get('prioridade') or payload.get('prioridade') or '').strip() or None
    tipo_pedido = (request.form.get('tipo_pedido') or payload.get('tipo_pedido') or '').strip() or None

    return {
        'project_raw': project_raw,
        'descricao': descricao,
        'status': status,
        'responsavel': responsavel,
        'prioridade': prioridade,
        'tipo_pedido': tipo_pedido,
    }


def _create_task_common(default_project=None):
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )

    payload = _extract_creation_payload(default_project=default_project)

    project, project_error, status_code = _resolve_project_token(payload['project_raw'], allow_empty=True)
    if project_error:
        if is_ajax:
            return jsonify({'success': False, 'message': project_error}), status_code
        flash(project_error, 'danger')
        return redirect(url_for('main.list_tasks'))

    status = payload['status'] if payload['status'] in VALID_STATUSES else 'programado'
    prioridade = payload['prioridade'] if payload['prioridade'] in VALID_PRIORIDADES else None
    tipo_pedido = payload['tipo_pedido'] if payload['tipo_pedido'] in VALID_TIPOS else None

    if not payload['descricao']:
        message = 'Descrição é obrigatória.'
        if is_ajax:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'danger')
        return redirect(url_for('main.list_tasks'))

    is_valid_responsavel, canonical_responsavel, invalid_names = _validate_task_responsavel(project, payload['responsavel'])
    if not is_valid_responsavel:
        message = _format_invalid_responsavel_message(invalid_names)
        if is_ajax:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'danger')
        return redirect(url_for('main.list_tasks'))

    try:
        max_ordem = (
            db.session.query(db.func.max(Task.ordem))
            .filter(Task.project_id == (project.id if project else None), Task.is_archived.is_(False))
            .scalar()
            or 0
        )

        task = Task(
            descricao=payload['descricao'],
            status=status,
            responsavel=canonical_responsavel if canonical_responsavel else None,
            prioridade=prioridade,
            tipo_pedido=tipo_pedido,
            project_id=project.id if project else None,
            created_by_id=g.user.id,
            ordem=max_ordem + 1,
        )

        db.session.add(task)
        db.session.flush()

        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_created',
            title='Nova tarefa',
            message=(
                f'{g.user.name} criou a tarefa "{_preview_text(task.descricao, 90)}" '
                f'com status {_task_status_label(task.status)}.'
            ),
        )
        if task.responsavel:
            notify_task_assignment_change(
                task,
                task,
                g.user.id,
                old_responsavel=None,
                new_responsavel=task.responsavel,
            )

        db.session.commit()

        if is_ajax:
            serialized = _serialize_task_payload(task)
            return jsonify({'success': True, 'task': serialized, 'item': serialized})

        flash('Tarefa adicionada com sucesso!', 'success')
        if project:
            return redirect(url_for('main.project_tasks', project_id=project.id))
        return redirect(url_for('main.list_tasks'))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao adicionar tarefa: {str(e)}', 'danger')
        return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas', methods=['GET'])
@login_required
def list_tasks():
    return _render_task_hub()


@main_bp.route('/tarefas/arquivadas', methods=['GET'])
@login_required
def list_tasks_archived():
    return _render_task_hub(include_archived=True)


@main_bp.route('/tarefas/finalizadas', methods=['GET'])
@login_required
def list_tasks_finalized():
    return redirect(f'{url_for("main.list_tasks_archived")}{_build_legacy_query_args()}')


@main_bp.route('/tarefas/add', methods=['POST'])
@login_required
def add_task():
    return _create_task_common()


@main_bp.route('/tarefas/<int:task_id>', methods=['GET'])
@login_required
def task_detail(task_id):
    task = db.session.get(Task, task_id)

    if task and _can_view_task(g.user, task):
        if task.project_id:
            return redirect(url_for('main.project_tasks', project_id=task.project_id, focus_task=task.id))
        return redirect(url_for('main.list_tasks', focus_task=task.id))

    legacy = LegacyTaskRedirect.query.filter_by(legacy_task_id=task_id).first()
    if legacy:
        if legacy.project_id:
            params = {}
            if legacy.sample_task_id:
                params['focus_task'] = legacy.sample_task_id
            return redirect(url_for('main.project_tasks', project_id=legacy.project_id, **params))
        params = {}
        if legacy.sample_task_id:
            params['focus_task'] = legacy.sample_task_id
        return redirect(url_for('main.list_tasks', **params))

    flash('Tarefa não encontrada.', 'warning')
    return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas/<int:task_id>/edit', methods=['POST'])
@login_required
def edit_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}

    incoming_descricao = request.form.get('descricao')
    if incoming_descricao is None:
        incoming_descricao = payload.get('descricao')
    if incoming_descricao is None:
        incoming_descricao = request.form.get('titulo')
    if incoming_descricao is None:
        incoming_descricao = payload.get('titulo')
    if incoming_descricao is None:
        incoming_descricao = task.descricao
    incoming_descricao = (incoming_descricao or '').strip()

    incoming_status = request.form.get('status')
    if incoming_status is None:
        incoming_status = payload.get('status')
    if incoming_status is None:
        incoming_status = task.status
    incoming_status = (incoming_status or '').strip()
    if incoming_status not in VALID_STATUSES:
        incoming_status = task.status

    project_raw = request.form.get('project')
    if project_raw is None:
        project_raw = request.form.get('project_id')
    if project_raw is None:
        project_raw = payload.get('project')
    if project_raw is None:
        project_raw = payload.get('project_id')

    if project_raw is None:
        project = task.project
    else:
        project, project_error, status_code = _resolve_project_token(project_raw, allow_empty=True)
        if project_error:
            return jsonify({'success': False, 'message': project_error}), status_code

    if 'responsavel' in request.form or 'responsavel' in payload:
        incoming_responsavel = (request.form.get('responsavel') or payload.get('responsavel') or '').strip()
    else:
        incoming_responsavel = task.responsavel or ''

    if 'prioridade' in request.form or 'prioridade' in payload:
        incoming_prioridade = (request.form.get('prioridade') or payload.get('prioridade') or '').strip() or None
        if incoming_prioridade and incoming_prioridade not in VALID_PRIORIDADES:
            incoming_prioridade = None
    else:
        incoming_prioridade = task.prioridade

    if 'tipo_pedido' in request.form or 'tipo_pedido' in payload:
        incoming_tipo = (request.form.get('tipo_pedido') or payload.get('tipo_pedido') or '').strip() or None
        if incoming_tipo is None:
            resolved_tipo = None
        elif incoming_tipo in VALID_TIPOS:
            resolved_tipo = incoming_tipo
        elif incoming_tipo in LEGACY_TIPOS and task.tipo_pedido in LEGACY_TIPOS:
            resolved_tipo = task.tipo_pedido
        else:
            resolved_tipo = None
    else:
        resolved_tipo = task.tipo_pedido

    if not incoming_descricao:
        return jsonify({'success': False, 'message': 'Descrição é obrigatória'}), 400

    is_valid_responsavel, resolved_responsavel, invalid_names = _resolve_responsavel_for_edit(
        task,
        incoming_responsavel,
        project,
    )
    if not is_valid_responsavel:
        return jsonify({'success': False, 'message': _format_invalid_responsavel_message(invalid_names)}), 400

    old_descricao = task.descricao
    old_status = task.status
    old_responsavel = task.responsavel
    old_prioridade = task.prioridade
    old_tipo = task.tipo_pedido
    old_project_id = task.project_id

    task.descricao = incoming_descricao
    task.status = incoming_status
    task.responsavel = resolved_responsavel if resolved_responsavel else None
    task.prioridade = incoming_prioridade
    task.tipo_pedido = resolved_tipo
    task.project_id = project.id if project else None

    try:
        changes = []
        if old_descricao != task.descricao:
            changes.append('descrição')
        if old_status != task.status:
            changes.append(f'status para {_task_status_label(task.status)}')
        if old_prioridade != task.prioridade:
            changes.append(f'prioridade para "{task.prioridade or "vazio"}"')
        if old_tipo != task.tipo_pedido:
            changes.append(f'tipo para "{task.tipo_pedido or "vazio"}"')
        if old_project_id != task.project_id:
            changes.append('projeto')

        if changes:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_updated',
                title='Tarefa atualizada',
                message=f'{g.user.name} atualizou "{_preview_text(task.descricao, 90)}": {", ".join(changes)}.',
            )

        if (old_responsavel or '') != (task.responsavel or ''):
            notify_task_assignment_change(
                task,
                task,
                g.user.id,
                old_responsavel=old_responsavel,
                new_responsavel=task.responsavel,
            )

        db.session.commit()
        serialized = _serialize_task_payload(task)
        return jsonify({
            'success': True,
            'message': 'Tarefa atualizada',
            'task': serialized,
            'item': serialized,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Tarefa não encontrada.', 'item_id': task_id}), 404
        flash('Tarefa não encontrada.', 'warning')
        return _redirect_back_or('main.list_tasks')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    if not _can_view_task(g.user, task):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para excluir esta tarefa.', 'item_id': task_id}), 403
        flash('Você não tem permissão para excluir esta tarefa.', 'danger')
        return _redirect_back_or('main.list_tasks')

    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_deleted',
            title='Tarefa excluída',
            message=f'{g.user.name} excluiu "{_preview_text(task.descricao, 90)}".',
            target_url=url_for('main.list_tasks'),
        )
        db.session.delete(task)
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Tarefa excluída com sucesso!', 'item_id': task_id})
        flash('Tarefa excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e), 'item_id': task_id}), 500
        flash(f'Erro ao excluir tarefa: {str(e)}', 'danger')

    return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/<int:task_id>/update_status', methods=['POST'])
@login_required
def update_task_status(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    status = payload.get('status')
    if status not in VALID_STATUSES:
        return jsonify({'success': False, 'message': 'Status inválido'}), 400

    old_status = task.status
    task.status = status

    try:
        if old_status != task.status:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_status_updated',
                title='Status atualizado',
                message=(
                    f'{g.user.name} alterou o status da tarefa "{_preview_text(task.descricao, 90)}" '
                    f'de {_task_status_label(old_status)} para {_task_status_label(task.status)}.'
                ),
            )
        db.session.commit()
        return jsonify({'success': True, 'message': 'Status atualizado'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/update_prioridade', methods=['POST'])
@login_required
def update_task_prioridade(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    prioridade = payload.get('prioridade', '') or None
    if prioridade and prioridade not in VALID_PRIORIDADES:
        return jsonify({'success': False, 'message': 'Prioridade inválida'}), 400

    old_prioridade = task.prioridade
    task.prioridade = prioridade

    try:
        if old_prioridade != task.prioridade:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_priority_updated',
                title='Prioridade atualizada',
                message=(
                    f'{g.user.name} alterou a prioridade da tarefa "{_preview_text(task.descricao, 90)}" '
                    f'de "{old_prioridade or "vazio"}" para "{task.prioridade or "vazio"}".'
                ),
            )
        db.session.commit()
        return jsonify({'success': True, 'prioridade': task.prioridade or ''})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/update_tipo', methods=['POST'])
@login_required
def update_task_tipo(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    tipo = payload.get('tipo_pedido', '') or None
    if tipo and tipo not in VALID_TIPOS:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    old_tipo = task.tipo_pedido
    task.tipo_pedido = tipo

    try:
        if old_tipo != task.tipo_pedido:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_type_updated',
                title='Tipo atualizado',
                message=(
                    f'{g.user.name} alterou o tipo da tarefa "{_preview_text(task.descricao, 90)}" '
                    f'de "{old_tipo or "vazio"}" para "{task.tipo_pedido or "vazio"}".'
                ),
            )
        db.session.commit()
        return jsonify({'success': True, 'tipo_pedido': task.tipo_pedido or ''})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


def _archive_task(task):
    task.is_archived = True
    task.archived_at = utc_now()


@main_bp.route('/tarefas/<int:task_id>/finalizar', methods=['POST'])
@login_required
def finalize_task(task_id):
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )
    task = db.session.get(Task, task_id)
    if not task or not _can_view_task(g.user, task):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Você não tem permissão para finalizar esta tarefa.'}), 403
        flash('Você não tem permissão para finalizar esta tarefa.', 'danger')
        return _redirect_back_or('main.list_tasks')

    if task.is_archived:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Esta tarefa já está arquivada.'}), 400
        flash('Esta tarefa já está arquivada.', 'info')
        return _redirect_back_or('main.list_tasks_archived')

    try:
        old_status = task.status
        task.status = 'finalizado'
        if old_status != task.status:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_finalized',
                title='Tarefa finalizada',
                message=f'{g.user.name} finalizou a tarefa "{_preview_text(task.descricao, 90)}".',
                target_url=_task_active_target_url(task),
            )
        db.session.commit()
        if is_ajax:
            serialized = _serialize_task_payload(task)
            return jsonify({'success': True, 'task': serialized, 'item': serialized})
        flash('Tarefa finalizada com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao finalizar tarefa: {str(e)}', 'danger')

    return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/<int:task_id>/desarquivar', methods=['POST'])
@login_required
def unarchive_task(task_id):
    task = db.session.get(Task, task_id)
    if not task or not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    task.is_archived = False
    task.archived_at = None
    task.status = 'programado'

    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_unarchived',
            title='Tarefa desarquivada',
            message=f'{g.user.name} desarquivou "{_preview_text(task.descricao, 90)}".',
            target_url=url_for('main.list_tasks'),
        )
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            serialized = _serialize_task_payload(task)
            return jsonify({'success': True, 'task': serialized, 'item': serialized})
        flash('Tarefa desarquivada com sucesso!', 'success')
        return _redirect_back_or('main.list_tasks')
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao desarquivar tarefa: {str(e)}', 'danger')
        return _redirect_back_or('main.list_tasks_archived')


@main_bp.route('/tarefas/<int:task_id>/reativar', methods=['POST'])
@login_required
def reactivate_task(task_id):
    return unarchive_task(task_id)


@main_bp.route('/tarefas/arquivar-finalizadas', methods=['POST'])
@login_required
def archive_finalized_tasks():
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )

    payload = request.get_json(silent=True) or {}
    filter_values = _merge_task_filter_values(
        _read_task_filter_values(payload),
        _read_task_filter_values(request.form),
    )
    selected_area = filter_values['selected_area']
    project_filter = filter_values['project_filter']
    prioridade_filter = filter_values['prioridade_filter']
    tipo_filter = filter_values['tipo_filter']
    status_filter = filter_values['status_filter']
    responsavel_filter = filter_values['responsavel_filter']

    query = _build_visible_tasks_query(
        include_archived=False,
        selected_area=selected_area,
        project_filter=project_filter,
        prioridade_filter=prioridade_filter,
        tipo_filter=tipo_filter,
        status_filter=status_filter,
        responsavel_filter=responsavel_filter,
        include_relations=False,
    ).filter(Task.status == 'finalizado')

    tasks = query.all()
    archived_count = 0
    archived_task_ids = []
    now = utc_now()

    try:
        for task in tasks:
            task.is_archived = True
            task.archived_at = now
            archived_count += 1
            archived_task_ids.append(str(task.id))
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_archived',
                title='Tarefa arquivada',
                message=f'{g.user.name} arquivou a tarefa "{_preview_text(task.descricao, 90)}".',
                target_url=url_for('main.list_tasks_archived'),
            )
        db.session.commit()

        if is_ajax:
            return jsonify({
                'success': True,
                'archived_count': archived_count,
                'archived_task_ids': archived_task_ids,
                'message': f'{archived_count} tarefa(s) arquivada(s).' if archived_count else 'Nenhuma tarefa finalizada para arquivar no escopo atual.',
            })

        if archived_count:
            flash(f'{archived_count} tarefa(s) finalizada(s) arquivada(s).', 'success')
        else:
            flash('Nenhuma tarefa finalizada para arquivar no escopo atual.', 'info')
        return _redirect_back_or('main.list_tasks')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao arquivar tarefas: {str(e)}', 'danger')
        return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/sugestoes-responsavel', methods=['GET'])
@login_required
def get_hub_assignable_users():
    project_raw = (request.args.get('project') or '').strip()
    area_raw = (request.args.get('area') or '').strip()

    if project_raw:
        project, project_error, status_code = _resolve_project_token(project_raw, allow_empty=False)
        if project_error:
            return jsonify({'success': False, 'message': project_error}), status_code
        users = _get_assignable_users_for_project(project)
    elif area_raw:
        users = _get_assignable_users_for_area(area_raw)
    else:
        return jsonify({'success': False, 'message': 'Informe um projeto ou área.'}), 400

    payload = [{'id': user.id, 'name': user.name} for user in users]

    q = (request.args.get('q') or '').strip().lower()
    if q:
        payload = [user for user in payload if q in (user['name'] or '').lower()]

    return jsonify({'users': payload})


@main_bp.route('/tarefas/<int:task_id>/sugestoes-responsavel', methods=['GET'])
@login_required
def get_task_assignable_users(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    users = _get_assignable_users_for_project(task.project)
    payload = [{'id': user.id, 'name': user.name} for user in users]

    q = (request.args.get('q') or '').strip().lower()
    if q:
        payload = [user for user in payload if q in (user['name'] or '').lower()]

    return jsonify({'users': payload})


@main_bp.route('/tarefas/<int:task_id>/comentarios/add', methods=['POST'])
@login_required
def add_task_comment(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'

    if not _can_view_task(g.user, task):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para comentar.'}), 403
        flash('Você não tem permissão para comentar nesta tarefa.', 'danger')
        return redirect(url_for('main.list_tasks'))

    content = request.form.get('content', '').strip()
    if not content:
        if is_ajax:
            return jsonify({'success': False, 'message': 'O comentário não pode estar vazio.'}), 400
        flash('O comentário não pode estar vazio.', 'warning')
        return redirect(url_for('main.list_tasks'))

    comment = TaskComment(content=content, user_id=g.user.id, task_id=task_id)

    try:
        db.session.add(comment)
        db.session.flush()
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_comment_added',
            title='Novo comentário em tarefa',
            message=f'{g.user.name} comentou: "{_preview_text(comment.content, 120)}".',
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
                    'is_own': True,
                },
            })

        flash('Comentário adicionado.', 'success')
        return redirect(url_for('main.list_tasks'))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao adicionar comentário: {str(e)}', 'danger')
        return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas/comentarios/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_task_item_comment(comment_id):
    comment = db.session.get(TaskComment, comment_id)
    if not comment:
        return jsonify({'success': False, 'message': 'Comentário não encontrado.'}), 404

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'

    if comment.user_id != g.user.id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Você só pode editar seus próprios comentários.'}), 403
        flash('Você só pode editar seus próprios comentários.', 'danger')
        return redirect(url_for('main.list_tasks'))

    content = request.form.get('content', '').strip()
    if not content:
        if is_ajax:
            return jsonify({'success': False, 'message': 'O comentário não pode estar vazio.'}), 400
        flash('O comentário não pode estar vazio.', 'warning')
        return redirect(url_for('main.list_tasks'))

    old_content = comment.content
    comment.content = content
    comment.updated_at = utc_now()

    try:
        notify_task_event(
            comment.task,
            actor_user_id=g.user.id,
            event_type='task_comment_updated',
            title='Comentário atualizado em tarefa',
            message=(
                f'{g.user.name} editou um comentário na tarefa "{_preview_text(comment.task.descricao, 90)}": '
                f'"{_preview_text(old_content, 70)}" -> "{_preview_text(comment.content, 70)}".'
            ),
        )
        db.session.commit()

        if is_ajax:
            return jsonify({
                'success': True,
                'comment': {
                    'id': comment.id,
                    'content': comment.content,
                    'updated_at': format_local_time(comment.updated_at) if comment.updated_at else None,
                },
            })

        flash('Comentário atualizado.', 'success')
        return redirect(url_for('main.list_tasks'))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao atualizar comentário: {str(e)}', 'danger')
        return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas/comentarios/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_task_item_comment(comment_id):
    comment = db.session.get(TaskComment, comment_id)
    if not comment:
        return jsonify({'success': False, 'message': 'Comentário não encontrado.', 'comment_id': comment_id}), 404

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'

    if comment.user_id != g.user.id:
        message = 'Você só pode excluir seus próprios comentários.'
        if is_ajax:
            return jsonify({'success': False, 'message': message, 'comment_id': comment_id}), 403
        flash(message, 'danger')
        return redirect(url_for('main.list_tasks'))

    try:
        notify_task_event(
            comment.task,
            actor_user_id=g.user.id,
            event_type='task_comment_deleted',
            title='Comentário removido em tarefa',
            message=f'{g.user.name} removeu um comentário na tarefa "{_preview_text(comment.task.descricao, 90)}".',
        )
        db.session.delete(comment)
        db.session.commit()

        if is_ajax:
            return jsonify({'success': True, 'message': 'Comentário excluído.', 'comment_id': comment_id})

        flash('Comentário excluído.', 'success')
        return redirect(url_for('main.list_tasks'))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e), 'comment_id': comment_id}), 500
        flash(f'Erro ao excluir comentário: {str(e)}', 'danger')
        return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas/<int:task_id>/anexos', methods=['GET'])
@login_required
def list_task_anexos(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
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
            for a in task.anexos
        ],
        'count': len(task.anexos),
    })


@main_bp.route('/tarefas/<int:task_id>/anexos/add', methods=['POST'])
@login_required
def add_task_anexo(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
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

    anexo = TaskAnexo(
        task_id=task_id,
        filename=original_name,
        stored_filename=stored_name,
        content_type=content_type,
        uploaded_by_id=g.user.id,
    )

    try:
        db.session.add(anexo)
        db.session.flush()
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_attachment_added',
            title='Novo anexo em tarefa',
            message=f'{g.user.name} anexou "{_preview_text(anexo.filename, 90)}" à tarefa "{_preview_text(task.descricao, 90)}".',
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
            'anexos_count': len(task.anexos),
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
    anexo = db.session.get(TaskAnexo, anexo_id)
    if not anexo:
        return jsonify({'success': False, 'message': 'Anexo não encontrado.'}), 404
    if not _can_view_task(g.user, anexo.task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    upload_folder = _get_upload_folder()
    file_path = os.path.join(upload_folder, anexo.stored_filename)
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'Arquivo não encontrado.'}), 404

    return send_file(file_path, download_name=anexo.filename, as_attachment=False)


@main_bp.route('/tarefas/anexos/<int:anexo_id>/delete', methods=['POST'])
@login_required
def delete_task_item_anexo(anexo_id):
    anexo = db.session.get(TaskAnexo, anexo_id)
    if not anexo:
        return jsonify({'success': False, 'message': 'Anexo não encontrado.'}), 404

    task = anexo.task
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    upload_folder = _get_upload_folder()
    file_path = os.path.join(upload_folder, anexo.stored_filename)

    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_attachment_deleted',
            title='Anexo removido em tarefa',
            message=f'{g.user.name} removeu o anexo "{_preview_text(anexo.filename, 90)}" da tarefa "{_preview_text(task.descricao, 90)}".',
        )
        db.session.delete(anexo)
        db.session.commit()
        try:
            os.remove(file_path)
        except OSError:
            pass
        return jsonify({'success': True, 'message': 'Anexo excluído.', 'anexos_count': len(task.anexos)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/projeto/<int:project_id>/tarefas', methods=['GET'])
@login_required
def project_tasks(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        flash('Projeto não encontrado.', 'warning')
        return redirect(url_for('main.list_projects'))

    if not _can_access_project_in_tasks(project):
        flash('Você não tem permissão para acessar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    return _render_task_hub(locked_project=project, template_name='project_tasks.html')


# ==============================
# Aliases legados (/tarefas/itens/...)
# ==============================

@main_bp.route('/tarefas/itens/add', methods=['POST'])
@login_required
def add_task_item_global():
    return _create_task_common()


@main_bp.route('/tarefas/<int:task_id>/itens/add', methods=['POST'])
@login_required
def add_task_item(task_id):
    anchor = db.session.get(Task, task_id)
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )
    if not anchor:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Tarefa não encontrada.'}), 404
        flash('Tarefa não encontrada.', 'warning')
        return redirect(url_for('main.list_tasks'))
    if not _can_view_task(g.user, anchor):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para este projeto.'}), 403
        flash('Sem permissão para este projeto.', 'danger')
        return redirect(url_for('main.list_tasks'))
    default_project = anchor.project
    return _create_task_common(default_project=default_project)


@main_bp.route('/tarefas/itens/<int:item_id>/edit', methods=['POST'])
@login_required
def edit_task_item(item_id):
    return edit_task(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_task_item(item_id):
    return delete_task(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/update_status', methods=['POST'])
@login_required
def update_task_item_status(item_id):
    return update_task_status(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/update_prioridade', methods=['POST'])
@login_required
def update_task_item_prioridade(item_id):
    return update_task_prioridade(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/update_tipo', methods=['POST'])
@login_required
def update_task_item_tipo(item_id):
    return update_task_tipo(item_id)


@main_bp.route('/tarefas/<int:task_id>/itens/reordenar', methods=['POST'])
@login_required
def reorder_task_items(task_id):
    anchor = db.session.get(Task, task_id)
    if not anchor:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, anchor):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    ordem_items_raw = payload.get('ordem', [])
    if not isinstance(ordem_items_raw, list):
        ordem_items_raw = []

    ordem_ids = []
    seen = set()
    for raw_id in ordem_items_raw:
        try:
            task_id_value = int(raw_id)
        except (TypeError, ValueError):
            continue
        if task_id_value in seen:
            continue
        seen.add(task_id_value)
        ordem_ids.append(task_id_value)

    scope_query = Task.query.filter(
        Task.project_id == anchor.project_id,
        Task.is_archived.is_(False),
    ).order_by(Task.ordem.asc(), Task.id.asc())

    if anchor.project_id is None and not g.user.is_admin:
        scope_query = scope_query.filter(Task.created_by_id == g.user.id)

    scope_tasks = scope_query.all()
    tasks_by_id = {t.id: t for t in scope_tasks}

    ordered_tasks = [tasks_by_id[t_id] for t_id in ordem_ids if t_id in tasks_by_id]
    ordered_ids = {t.id for t in ordered_tasks}
    remaining = [t for t in scope_tasks if t.id not in ordered_ids]
    final_order = ordered_tasks + remaining

    try:
        for index, task in enumerate(final_order, start=1):
            task.ordem = index
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ordem atualizada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/itens/<int:item_id>/comentarios/add', methods=['POST'])
@login_required
def add_task_item_comment(item_id):
    return add_task_comment(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/anexos', methods=['GET'])
@login_required
def list_task_item_anexos(item_id):
    return list_task_anexos(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/anexos/add', methods=['POST'])
@login_required
def add_task_item_anexo(item_id):
    return add_task_anexo(item_id)
