from urllib.parse import urlencode

from flask import g, request, url_for
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from models import (
    Project,
    Task,
    TaskComment,
    db,
)
from routes.tasks.constants import (
    TASK_PRIORIDADE_ORDER,
    TASK_STATUS_ORDER,
    TASK_TIPO_ORDER,
    _normalize_person_name,
    _split_responsavel_names,
    _task_prioridade_label,
    _task_status_label,
    _task_tipo_label,
)


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
