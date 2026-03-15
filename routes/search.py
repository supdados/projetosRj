import datetime
from zoneinfo import ZoneInfo

from flask import g, jsonify, render_template, request, url_for
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import joinedload

from models import CalendarEvent, Etapa, Project, Task

from .blueprint import main_bp
from .decorators import login_required
from .shared import redirect_to_current_route_without_area, sanitize_area_filter_for_current_user, sanitize_area_filter_for_user

GLOBAL_SEARCH_DEFAULT_LIMIT = 5
GLOBAL_SEARCH_API_MAX_LIMIT = 20
GLOBAL_SEARCH_PAGE_LIMIT = 50
TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')


def _truncate_text(value, max_length=140):
    text_value = ' '.join((value or '').split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + '...'


def _build_match_excerpt(value, term, max_length=110):
    text_value = ' '.join((value or '').split())
    if not text_value:
        return ''

    normalized_term = (term or '').strip().lower()
    if not normalized_term:
        return _truncate_text(text_value, max_length)

    lowered_value = text_value.lower()
    match_index = lowered_value.find(normalized_term)
    if match_index == -1:
        return _truncate_text(text_value, max_length)

    context_before = max_length // 3
    start = max(0, match_index - context_before)
    end = min(len(text_value), start + max_length)
    snippet = text_value[start:end].strip()

    if start > 0:
        snippet = f'...{snippet}'
    if end < len(text_value):
        snippet = f'{snippet}...'
    return snippet


def _build_project_display_title(project, max_length=120):
    base_title = project.titulo or f'Projeto #{project.id}'
    return _truncate_text(f'{project.id}-{base_title}', max_length)


def _to_local_datetime(utc_naive):
    if utc_naive is None:
        return None
    return utc_naive.replace(tzinfo=datetime.UTC).astimezone(TIMEZONE_BR)


def _format_calendar_event_period(event):
    if not event.starts_at:
        return ''

    starts_at = _to_local_datetime(event.starts_at)
    ends_at = _to_local_datetime(event.ends_at)

    if event.is_all_day:
        display_end = starts_at.date()
        if ends_at:
            display_end = ends_at.date()
            if ends_at > starts_at and ends_at.time() == datetime.time(0, 0):
                display_end = (ends_at - datetime.timedelta(days=1)).date()
            if display_end < starts_at.date():
                display_end = starts_at.date()
        if display_end != starts_at.date():
            return f'{starts_at:%d/%m/%Y} ate {display_end:%d/%m/%Y}'
        return starts_at.strftime('%d/%m/%Y')

    if ends_at:
        if starts_at.date() == ends_at.date():
            return f'{starts_at:%d/%m/%Y} {starts_at:%H:%M} - {ends_at:%H:%M}'
        return f'{starts_at:%d/%m/%Y %H:%M} - {ends_at:%d/%m/%Y %H:%M}'

    return starts_at.strftime('%d/%m/%Y %H:%M')


def _resolve_match_info(term, ordered_fields):
    normalized_term = (term or '').strip().lower()
    if not normalized_term:
        return {
            'match_field': '',
            'match_label': '',
            'match_excerpt': '',
        }

    for field_name, field_label, field_value in ordered_fields:
        normalized_value = ' '.join((field_value or '').split())
        if not normalized_value:
            continue
        if normalized_term in normalized_value.lower():
            return {
                'match_field': field_name,
                'match_label': field_label,
                'match_excerpt': _build_match_excerpt(normalized_value, term),
            }

    return {
        'match_field': '',
        'match_label': '',
        'match_excerpt': '',
    }


def _empty_global_search_payload(term):
    normalized = (term or '').strip()
    return {
        'query': normalized,
        'meta': {
            'limit_per_type': None,
            'has_more': {
                'projects': False,
                'stages': False,
                'tasks': False,
                'events': False,
                'any': False,
            },
        },
        'counts': {
            'projects': 0,
            'stages': 0,
            'tasks': 0,
            'events': 0,
            'total': 0,
        },
        'results': {
            'projects': [],
            'stages': [],
            'tasks': [],
            'events': [],
        },
    }


def _normalize_global_search_limit(raw_limit, default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT, max_limit=GLOBAL_SEARCH_API_MAX_LIMIT):
    if raw_limit is None or raw_limit == '':
        return default_limit
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        return default_limit
    return max(1, min(parsed, max_limit))


def build_global_search_results(term, user, limit_per_type=None, include_has_more=False, selected_area=''):
    normalized_term = (term or '').strip()
    if not normalized_term:
        return _empty_global_search_payload(normalized_term)

    search_pattern = f'%{normalized_term}%'
    prefix_pattern = f'{normalized_term.lower()}%'

    user_areas = user.get_areas() if (user and not user.is_admin) else []

    # Compute effective area restriction
    selected_area, invalid_area_filter = sanitize_area_filter_for_user(user, selected_area)
    if invalid_area_filter:
        selected_area = ''

    if selected_area:
        if user.is_admin:
            filter_areas = [selected_area]
        elif selected_area in user_areas:
            filter_areas = [selected_area]
        else:
            filter_areas = []
        area_restricted = True
    else:
        filter_areas = user_areas
        area_restricted = not user.is_admin

    effective_limit = limit_per_type
    if include_has_more and limit_per_type is not None:
        effective_limit = limit_per_type + 1

    def apply_optional_limit(query):
        if effective_limit is not None:
            return query.limit(effective_limit)
        return query

    def trim_limited_rows(rows):
        if not include_has_more or limit_per_type is None:
            return rows, False
        if len(rows) > limit_per_type:
            return rows[:limit_per_type], True
        return rows, False

    def prefix_order_for(column):
        return case((func.lower(func.coalesce(column, '')).like(prefix_pattern), 0), else_=1)

    try:
        search_id = int(normalized_term)
    except ValueError:
        search_id = None

    project_id_filter = (Project.id == search_id) if search_id is not None else None

    project_text_filters = or_(
        Project.titulo.ilike(search_pattern),
        Project.orgao.ilike(search_pattern),
        Project.short_description.ilike(search_pattern),
        Project.observacao.ilike(search_pattern),
        Project.area_responsavel.ilike(search_pattern),
    )

    project_query = Project.query.filter(
        or_(project_id_filter, project_text_filters) if project_id_filter is not None else project_text_filters
    )
    if area_restricted:
        if filter_areas:
            project_query = project_query.filter(Project.area_responsavel.in_(filter_areas))
        else:
            project_query = project_query.filter(Project.id == -1)
    project_query = apply_optional_limit(project_query.order_by(prefix_order_for(Project.titulo), Project.id.desc()))
    projects = project_query.all()
    projects, projects_has_more = trim_limited_rows(projects)

    stage_query = Etapa.query.join(Project, Etapa.project_id == Project.id).options(joinedload(Etapa.project)).filter(
        or_(
            Etapa.descricao.ilike(search_pattern),
            Etapa.comentarios.ilike(search_pattern),
            Etapa.responsavel.ilike(search_pattern),
        )
    )
    if area_restricted:
        if filter_areas:
            stage_query = stage_query.filter(Project.area_responsavel.in_(filter_areas))
        else:
            stage_query = stage_query.filter(Project.id == -1)
    stage_query = apply_optional_limit(stage_query.order_by(prefix_order_for(Etapa.descricao), Etapa.id.desc()))
    stages = stage_query.all()
    stages, stages_has_more = trim_limited_rows(stages)

    task_query = Task.query.outerjoin(Project, Task.project_id == Project.id).options(joinedload(Task.project)).filter(
        or_(
            Task.descricao.ilike(search_pattern),
            Task.responsavel.ilike(search_pattern),
            Task.status.ilike(search_pattern),
            Task.prioridade.ilike(search_pattern),
            Task.tipo_pedido.ilike(search_pattern),
        )
    )
    if area_restricted:
        if filter_areas:
            if user.is_admin:
                task_query = task_query.filter(
                    Task.project_id.isnot(None),
                    Project.area_responsavel.in_(filter_areas),
                )
            else:
                task_query = task_query.filter(
                    or_(
                        and_(Task.project_id.isnot(None), Project.area_responsavel.in_(filter_areas)),
                        and_(Task.project_id.is_(None), Task.created_by_id == user.id),
                    )
                )
        else:
            task_query = task_query.filter(Task.id == -1)
    task_query = apply_optional_limit(task_query.order_by(prefix_order_for(Task.descricao), Task.id.desc()))
    tasks = task_query.all()
    tasks, tasks_has_more = trim_limited_rows(tasks)

    event_id_filter = (CalendarEvent.id == search_id) if search_id is not None else None
    event_text_filters = or_(
        CalendarEvent.title.ilike(search_pattern),
        CalendarEvent.description.ilike(search_pattern),
        CalendarEvent.location.ilike(search_pattern),
    )
    event_query = CalendarEvent.query.filter(
        CalendarEvent.user_id == user.id,
        or_(event_id_filter, event_text_filters) if event_id_filter is not None else event_text_filters,
    )
    event_query = apply_optional_limit(
        event_query.order_by(
            prefix_order_for(CalendarEvent.title),
            CalendarEvent.starts_at.desc(),
            CalendarEvent.id.desc(),
        )
    )
    events = event_query.all()
    events, events_has_more = trim_limited_rows(events)

    status_labels = {
        'nao_iniciada': 'Não iniciada',
        'em_andamento': 'Em andamento',
        'para_validacao': 'Para validação',
        'para_ajustes': 'Para ajustes',
        'finalizada': 'Finalizada',
    }

    project_results = [
        {
            'type': 'project',
            'type_label': 'Projeto',
            'title': _truncate_text(project.titulo or f'Projeto #{project.id}', 120),
            'display_title': _build_project_display_title(project),
            'subtitle': f'Orgao: {_truncate_text(project.orgao, 90)}' if project.orgao else '',
            'meta': f'Area: {project.area_responsavel}' if project.area_responsavel else 'Area nao informada',
            'url': url_for('main.project_detail', project_id=project.id),
            **_resolve_match_info(normalized_term, [
                ('titulo', 'Titulo', project.titulo),
                ('orgao', 'Orgao', project.orgao),
                ('short_description', 'Descricao curta', project.short_description),
                ('observacao', 'Observacao', project.observacao),
                ('area_responsavel', 'Area', project.area_responsavel),
            ]),
        }
        for project in projects
    ]

    stage_results = []
    for stage in stages:
        project = stage.project
        stage_match = _resolve_match_info(normalized_term, [
            ('descricao', 'Descricao', stage.descricao),
            ('comentarios', 'Comentario', stage.comentarios),
            ('responsavel', 'Responsavel', stage.responsavel),
        ])
        stage_results.append({
            'type': 'stage',
            'type_label': 'Etapa',
            'title': _truncate_text(stage.descricao or f'Etapa #{stage.id}', 120),
            'subtitle': f'Projeto: {_truncate_text(project.titulo, 95)}' if project else '',
            'meta': (
                f'Responsavel: {_truncate_text(stage.responsavel, 80)}'
                if stage.responsavel else
                'Responsavel nao informado'
            ),
            'url': url_for('main.project_detail', project_id=stage.project_id, focus_etapa=stage.id),
            **stage_match,
        })

    task_results = []
    for task in tasks:
        task_match = _resolve_match_info(normalized_term, [
            ('descricao', 'Descrição', task.descricao),
            ('responsavel', 'Responsável', task.responsavel),
            ('status', 'Status', task.status),
            ('prioridade', 'Prioridade', task.prioridade),
            ('tipo_pedido', 'Tipo', task.tipo_pedido),
        ])
        status_label = status_labels.get(task.status, task.status or '')
        task_meta_parts = []
        if status_label:
            task_meta_parts.append(f'Status: {status_label}')
        if task.responsavel:
            task_meta_parts.append(f'Responsavel: {_truncate_text(task.responsavel, 80)}')
        if task.prioridade:
            task_meta_parts.append(f'Prioridade: {task.prioridade}')

        task_results.append({
            'type': 'task',
            'type_label': 'Tarefa',
            'title': _truncate_text(task.descricao or f'Tarefa #{task.id}', 120),
            'subtitle': f'Projeto: {_truncate_text(task.project.titulo, 95)}' if task.project else 'Sem projeto',
            'meta': ' | '.join(task_meta_parts),
            'url': url_for('main.task_detail', task_id=task.id),
            **task_match,
        })

    event_sync_labels = {
        'pending': 'Pendente',
        'ok': 'Sincronizado',
        'error': 'Erro',
    }
    event_results = []
    for event in events:
        event_match = _resolve_match_info(normalized_term, [
            ('title', 'Titulo', event.title),
            ('description', 'Descricao', event.description),
            ('location', 'Local', event.location),
        ])
        event_meta_parts = []
        event_period = _format_calendar_event_period(event)
        if event_period:
            event_meta_parts.append(f'Quando: {event_period}')
        if event.location:
            event_meta_parts.append(f'Local: {_truncate_text(event.location, 80)}')
        sync_label = event_sync_labels.get(event.sync_status, event.sync_status or '')
        if sync_label:
            event_meta_parts.append(f'Sync: {sync_label}')

        event_results.append({
            'type': 'event',
            'type_label': 'Evento',
            'title': _truncate_text(event.title or f'Evento #{event.id}', 120),
            'subtitle': _truncate_text(event.description, 95) if event.description else '',
            'meta': ' | '.join(event_meta_parts),
            'url': url_for('main.calendars_hub'),
            **event_match,
        })

    counts = {
        'projects': len(project_results),
        'stages': len(stage_results),
        'tasks': len(task_results),
        'events': len(event_results),
    }
    counts['total'] = counts['projects'] + counts['stages'] + counts['tasks'] + counts['events']

    has_more = {
        'projects': projects_has_more,
        'stages': stages_has_more,
        'tasks': tasks_has_more,
        'events': events_has_more,
    }
    has_more_any = any(has_more.values())

    return {
        'query': normalized_term,
        'meta': {
            'limit_per_type': limit_per_type,
            'has_more': {
                **has_more,
                'any': has_more_any,
            },
        },
        'counts': counts,
        'results': {
            'projects': project_results,
            'stages': stage_results,
            'tasks': task_results,
            'events': event_results,
        },
    }


@main_bp.route('/api/busca-global', methods=['GET'])
@login_required
def global_search_api():
    search_term = (request.args.get('q') or '').strip()
    selected_area, _ = sanitize_area_filter_for_current_user(request.args.get('area'))
    limit_per_type = _normalize_global_search_limit(
        request.args.get('limit'),
        default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT,
        max_limit=GLOBAL_SEARCH_API_MAX_LIMIT,
    )

    if len(search_term) < 2:
        return jsonify(_empty_global_search_payload(search_term))

    payload = build_global_search_results(
        search_term,
        g.user,
        limit_per_type=limit_per_type,
        include_has_more=True,
        selected_area=selected_area,
    )
    return jsonify(payload)


@main_bp.route('/busca', methods=['GET'])
@login_required
def global_search_page():
    search_term = (request.args.get('q') or '').strip()
    selected_area, invalid_area_filter = sanitize_area_filter_for_current_user(request.args.get('area'))
    if invalid_area_filter:
        return redirect_to_current_route_without_area()
    if search_term:
        search_payload = build_global_search_results(
            search_term,
            g.user,
            limit_per_type=GLOBAL_SEARCH_PAGE_LIMIT,
            selected_area=selected_area,
        )
    else:
        search_payload = _empty_global_search_payload(search_term)

    return render_template(
        'search/results.html',
        search_query=search_term,
        search_payload=search_payload,
    )
