from flask import g, jsonify, render_template, request
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import joinedload

from models import Project, Task, TaskItem, Etapa

from .blueprint import main_bp
from .decorators import login_required
GLOBAL_SEARCH_DEFAULT_LIMIT = 5
GLOBAL_SEARCH_API_MAX_LIMIT = 20
GLOBAL_SEARCH_PAGE_LIMIT = 50


def _truncate_text(value, max_length=140):
    text_value = " ".join((value or "").split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + "..."


def _build_match_excerpt(value, term, max_length=110):
    text_value = " ".join((value or "").split())
    if not text_value:
        return ""

    normalized_term = (term or "").strip().lower()
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
        snippet = f"...{snippet}"
    if end < len(text_value):
        snippet = f"{snippet}..."
    return snippet


def _resolve_match_info(term, ordered_fields):
    normalized_term = (term or "").strip().lower()
    if not normalized_term:
        return {
            "match_field": "",
            "match_label": "",
            "match_excerpt": ""
        }

    for field_name, field_label, field_value in ordered_fields:
        normalized_value = " ".join((field_value or "").split())
        if not normalized_value:
            continue
        if normalized_term in normalized_value.lower():
            return {
                "match_field": field_name,
                "match_label": field_label,
                "match_excerpt": _build_match_excerpt(normalized_value, term),
            }

    return {
        "match_field": "",
        "match_label": "",
        "match_excerpt": ""
    }


def _empty_global_search_payload(term):
    normalized = (term or "").strip()
    return {
        "query": normalized,
        "counts": {
            "projects": 0,
            "stages": 0,
            "tasks": 0,
            "task_items": 0,
            "total": 0
        },
        "results": {
            "projects": [],
            "stages": [],
            "tasks": [],
            "task_items": []
        }
    }


def _normalize_global_search_limit(raw_limit, default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT, max_limit=GLOBAL_SEARCH_API_MAX_LIMIT):
    if raw_limit is None or raw_limit == "":
        return default_limit
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        return default_limit
    return max(1, min(parsed, max_limit))


def build_global_search_results(term, user, limit_per_type=None):
    normalized_term = (term or "").strip()
    if not normalized_term:
        return _empty_global_search_payload(normalized_term)

    search_pattern = f"%{normalized_term}%"
    prefix_pattern = f"{normalized_term.lower()}%"
    status_labels = {
        "programado": "Programado",
        "em_andamento": "Em andamento",
        "validacao": "Validacao",
        "finalizado": "Finalizado",
    }

    user_areas = user.get_areas() if (user and not user.is_admin) else []

    def apply_optional_limit(query):
        if limit_per_type is not None:
            return query.limit(limit_per_type)
        return query

    def prefix_order_for(column):
        return case(
            (func.lower(func.coalesce(column, "")).like(prefix_pattern), 0),
            else_=1
        )

    project_query = Project.query.filter(
        or_(
            Project.titulo.ilike(search_pattern),
            Project.orgao.ilike(search_pattern),
            Project.short_description.ilike(search_pattern),
            Project.observacao.ilike(search_pattern),
            Project.area_responsavel.ilike(search_pattern),
        )
    )
    if not user.is_admin:
        if user_areas:
            project_query = project_query.filter(Project.area_responsavel.in_(user_areas))
        else:
            project_query = project_query.filter(Project.id == -1)
    project_query = apply_optional_limit(
        project_query.order_by(prefix_order_for(Project.titulo), Project.id.desc())
    )
    projects = project_query.all()

    stage_query = Etapa.query.join(Project, Etapa.project_id == Project.id).options(joinedload(Etapa.project)).filter(
        or_(
            Etapa.descricao.ilike(search_pattern),
            Etapa.comentarios.ilike(search_pattern),
            Etapa.responsavel.ilike(search_pattern),
        )
    )
    if not user.is_admin:
        if user_areas:
            stage_query = stage_query.filter(Project.area_responsavel.in_(user_areas))
        else:
            stage_query = stage_query.filter(Project.id == -1)
    stage_query = apply_optional_limit(
        stage_query.order_by(prefix_order_for(Etapa.descricao), Etapa.id.desc())
    )
    stages = stage_query.all()

    task_query = Task.query.outerjoin(Project, Task.project_id == Project.id).options(joinedload(Task.project)).filter(
        Task.titulo.ilike(search_pattern)
    )
    if not user.is_admin:
        task_query = task_query.filter(
            or_(
                and_(Task.project_id.isnot(None), Project.area_responsavel.in_(user_areas)),
                and_(Task.project_id.is_(None), Task.created_by_id == user.id)
            )
        )
    task_query = apply_optional_limit(
        task_query.order_by(prefix_order_for(Task.titulo), Task.id.desc())
    )
    tasks = task_query.all()

    task_item_query = TaskItem.query.join(Task, TaskItem.task_id == Task.id).outerjoin(
        Project, Task.project_id == Project.id
    ).options(
        joinedload(TaskItem.task).joinedload(Task.project)
    ).filter(
        or_(
            TaskItem.descricao.ilike(search_pattern),
            TaskItem.responsavel.ilike(search_pattern),
        )
    )
    if not user.is_admin:
        task_item_query = task_item_query.filter(
            or_(
                and_(Task.project_id.isnot(None), Project.area_responsavel.in_(user_areas)),
                and_(Task.project_id.is_(None), Task.created_by_id == user.id)
            )
        )
    task_item_query = apply_optional_limit(
        task_item_query.order_by(prefix_order_for(TaskItem.descricao), TaskItem.id.desc())
    )
    task_items = task_item_query.all()

    project_results = [
        {
            "type": "project",
            "type_label": "Projeto",
            "title": _truncate_text(project.titulo or f"Projeto #{project.id}", 120),
            "subtitle": f"Orgao: {_truncate_text(project.orgao, 90)}" if project.orgao else "",
            "meta": f"Area: {project.area_responsavel}" if project.area_responsavel else "Area nao informada",
            "url": url_for('main.project_detail', project_id=project.id),
            **_resolve_match_info(normalized_term, [
                ("titulo", "Titulo", project.titulo),
                ("orgao", "Orgao", project.orgao),
                ("short_description", "Descricao curta", project.short_description),
                ("observacao", "Observacao", project.observacao),
                ("area_responsavel", "Area", project.area_responsavel),
            ]),
        }
        for project in projects
    ]

    stage_results = []
    for stage in stages:
        project = stage.project
        stage_match = _resolve_match_info(normalized_term, [
            ("descricao", "Descricao", stage.descricao),
            ("comentarios", "Comentario", stage.comentarios),
            ("responsavel", "Responsavel", stage.responsavel),
        ])
        stage_results.append({
            "type": "stage",
            "type_label": "Etapa",
            "title": _truncate_text(stage.descricao or f"Etapa #{stage.id}", 120),
            "subtitle": f"Projeto: {_truncate_text(project.titulo, 95)}" if project else "",
            "meta": (
                f"Responsavel: {_truncate_text(stage.responsavel, 80)}"
                if stage.responsavel else
                "Responsavel nao informado"
            ),
            "url": url_for('main.project_detail', project_id=stage.project_id, focus_etapa=stage.id),
            **stage_match,
        })

    task_results = []
    for task in tasks:
        task_match = _resolve_match_info(normalized_term, [
            ("titulo", "Titulo", task.titulo),
        ])
        task_results.append({
            "type": "task",
            "type_label": "Tarefa",
            "title": _truncate_text(task.titulo or f"Tarefa #{task.id}", 120),
            "subtitle": f"Projeto: {_truncate_text(task.project.titulo, 95)}" if task.project else "Sem projeto",
            "meta": (
                f"Criada em {task.created_at.strftime('%d/%m/%Y')}"
                if task.created_at else
                ""
            ),
            "url": url_for('main.task_detail', task_id=task.id),
            **task_match,
        })

    task_item_results = []
    for task_item in task_items:
        task_item_task = task_item.task
        task_item_match = _resolve_match_info(normalized_term, [
            ("descricao", "Descricao", task_item.descricao),
            ("responsavel", "Responsavel", task_item.responsavel),
        ])
        status_label = status_labels.get(task_item.status, task_item.status or "")
        task_item_meta_parts = []
        if status_label:
            task_item_meta_parts.append(f"Status: {status_label}")
        if task_item.responsavel:
            task_item_meta_parts.append(f"Responsavel: {_truncate_text(task_item.responsavel, 80)}")
        task_item_results.append({
            "type": "task_item",
            "type_label": "Item",
            "title": _truncate_text(task_item.descricao or f"Item #{task_item.id}", 120),
            "subtitle": (
                f"Tarefa: {_truncate_text(task_item_task.titulo, 95)}"
                if task_item_task else
                ""
            ),
            "meta": " | ".join(task_item_meta_parts),
            "url": url_for('main.task_detail', task_id=task_item.task_id, focus_item=task_item.id),
            **task_item_match,
        })

    counts = {
        "projects": len(project_results),
        "stages": len(stage_results),
        "tasks": len(task_results),
        "task_items": len(task_item_results),
    }
    counts["total"] = counts["projects"] + counts["stages"] + counts["tasks"] + counts["task_items"]

    return {
        "query": normalized_term,
        "counts": counts,
        "results": {
            "projects": project_results,
            "stages": stage_results,
            "tasks": task_results,
            "task_items": task_item_results,
        }
    }
@main_bp.route('/api/busca-global', methods=['GET'])
@login_required
def global_search_api():
    search_term = (request.args.get('q') or '').strip()
    limit_per_type = _normalize_global_search_limit(
        request.args.get('limit'),
        default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT,
        max_limit=GLOBAL_SEARCH_API_MAX_LIMIT
    )

    if len(search_term) < 2:
        return jsonify(_empty_global_search_payload(search_term))

    payload = build_global_search_results(search_term, g.user, limit_per_type=limit_per_type)
    return jsonify(payload)


@main_bp.route('/busca', methods=['GET'])
@login_required
def global_search_page():
    search_term = (request.args.get('q') or '').strip()
    if search_term:
        search_payload = build_global_search_results(
            search_term,
            g.user,
            limit_per_type=GLOBAL_SEARCH_PAGE_LIMIT
        )
    else:
        search_payload = _empty_global_search_payload(search_term)

    return render_template(
        'search_results.html',
        search_query=search_term,
        search_payload=search_payload
    )
