import os
import re
from urllib.parse import urlencode, urlparse

from flask import flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from models import (
    Project,
    Task,
    TaskAccessAudit,
    TaskComment,
    User,
    UserArea,
    db,
)
from services.notifications import notify_task_assignment_change, notify_task_event
from .shared import redirect_to_current_route_without_area, sanitize_area_filter_for_current_user

VALID_PRIORIDADES = {'baixa', 'media', 'alta', 'urgente'}
VALID_TIPOS = {'bug', 'melhoria', 'duvida', 'outros'}
LEGACY_TIPOS = {'implementacao'}
VALID_STATUSES = {'nao_iniciada', 'em_andamento', 'para_validacao', 'para_ajustes', 'finalizada'}
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}
TASK_PRIORIDADE_ORDER = ('baixa', 'media', 'alta', 'urgente')
TASK_TIPO_ORDER = ('bug', 'melhoria', 'duvida', 'outros', 'implementacao')
TASK_STATUS_ORDER = ('nao_iniciada', 'em_andamento', 'para_validacao', 'para_ajustes', 'finalizada')


def _get_upload_folder():
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    folder = os.path.join(basedir, 'instance', 'uploads', 'tasks')
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _task_status_label(status):
    labels = {
        'nao_iniciada': 'Não iniciada',
        'em_andamento': 'Em andamento',
        'para_validacao': 'Para validação',
        'para_ajustes': 'Para ajustes',
        'finalizada': 'Finalizada',
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
        for value in TASK_STATUS_ORDER
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


def _can_manage_task_restricted_actions(user, task):
    return bool(user and task and (user.is_admin or task.created_by_id == user.id))


def _can_transition_task_to_status(user, task, next_status, previous_status=None):
    normalized_next_status = (next_status or '').strip()
    normalized_previous_status = (previous_status or task.status or '').strip()

    if normalized_next_status != 'finalizada':
        return True

    if normalized_previous_status == 'finalizada':
        return True

    return _can_manage_task_restricted_actions(user, task)


def _audit_denied_task_action(task, action_type, *, attempted_status=None):
    actor = getattr(g, 'user', None)
    if not task or not actor:
        return

    try:
        db.session.add(
            TaskAccessAudit(
                task_id=task.id,
                project_id=task.project_id,
                actor_user_id=actor.id,
                actor_name=actor.name or actor.username or 'Usuário',
                task_author_user_id=task.created_by_id,
                action_type=action_type,
                reason='not_task_author',
                attempted_status=attempted_status,
                task_description=_preview_text(task.descricao, 240) or f'Tarefa #{task.id}',
            )
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f'Erro ao auditar tentativa negada em tarefa: {exc}')


def _task_permission_flags(task, user=None):
    actor = user or getattr(g, 'user', None)
    can_manage = _can_manage_task_restricted_actions(actor, task)
    return {
        'can_delete': can_manage,
        'can_finalize': can_manage,
        'is_author': bool(actor and task and task.created_by_id == actor.id),
    }


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
    permission_flags = _task_permission_flags(task)
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
        'project_area': project.area_responsavel if project else '',
        'project_value': str(project_id) if project_id else 'sem_projeto',
        'comments_count': len(task.comments),
        'anexos_count': len(task.anexos),
        'can_delete': permission_flags['can_delete'],
        'can_finalize': permission_flags['can_finalize'],
        'is_author': permission_flags['is_author'],
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
        permission_flags = _task_permission_flags(task)
        task.hub_can_delete = permission_flags['can_delete']
        task.hub_can_finalize = permission_flags['can_finalize']
        task.hub_is_author = permission_flags['is_author']

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


def _build_task_hub_project_options(include_archived=False, selected_area=''):
    area_scope, normalized_area = _resolve_task_hub_area_scope(selected_area)

    query = Project.query

    if not g.user.is_admin:
        if area_scope:
            query = query.filter(Project.area_responsavel.in_(area_scope))
        else:
            query = query.filter(db.false())

    if normalized_area:
        query = query.filter(Project.area_responsavel == normalized_area)

    projects = query.order_by(db.func.lower(Project.titulo), Project.titulo.asc(), Project.id.asc()).all()
    options = [
        {
            'value': str(project.id),
            'label': project.titulo,
            'area': project.area_responsavel,
        }
        for project in projects
    ]

    has_orphan_tasks = (
        _build_visible_tasks_query(
            include_archived=include_archived,
            selected_area=selected_area,
            project_filter='sem_projeto',
            include_relations=False,
        )
        .limit(1)
        .first()
        is not None
    )
    if has_orphan_tasks:
        options.append(
            {
                'value': 'sem_projeto',
                'label': 'Sem projeto',
                'area': '',
            }
        )

    return options


def _render_task_hub(locked_project=None, template_name='task_hub.html', include_archived=False):
    filter_values = _read_task_filter_values(request.args)
    selected_area, invalid_area_filter = sanitize_area_filter_for_current_user(filter_values['selected_area'])
    if invalid_area_filter and locked_project is None:
        return redirect_to_current_route_without_area()
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

    project_options = _build_task_hub_project_options(
        include_archived=include_archived,
        selected_area=selected_area,
    )

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
    filter_form_endpoint = 'main.list_tasks_archived' if include_archived else 'main.list_tasks'
    filter_form_action = _build_task_listing_url(
        filter_form_endpoint,
    )
    clear_endpoint = 'main.list_tasks_archived' if include_archived else 'main.list_tasks'
    clear_url = _build_task_listing_url(
        clear_endpoint,
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

    status = (request.form.get('status') or payload.get('status') or 'nao_iniciada').strip()
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

    status = payload['status'] if payload['status'] in VALID_STATUSES else 'nao_iniciada'
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
