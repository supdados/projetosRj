from urllib.parse import urlencode

from flask import g, request, url_for
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from models import (
    Project,
    Task,
    TaskAssignee,
    TaskComment,
    User,
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


def assignee_initials(name: str) -> str:
    """Iniciais para o avatar (sem foto): 1ª letra do 1º e do último nome.

    Exemplo: "Alex Johnson" -> "AJ"; "Maria" -> "MA"; vazio -> "?".
    """
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def serialize_assignee(user: User) -> dict:
    """Serializa um usuário como responsável: {id, name, initials, subtitle}."""
    display_name = user.name or user.username or "Usuário"
    subtitle = (user.orgao or "").strip() or f"@{user.username}"
    return {
        "id": user.id,
        "name": display_name,
        "initials": assignee_initials(user.name or user.username),
        "subtitle": subtitle,
    }


def serialize_task_assignees(task: Task) -> list:
    """Lista serializada dos responsáveis de uma tarefa (ordenados por nome)."""
    rows = [a for a in task.assignees if a.user is not None]
    rows.sort(key=lambda a: (a.user.name or a.user.username or "").lower())
    return [serialize_assignee(a.user) for a in rows]


def set_task_assignees(task: Task, desired_user_ids) -> tuple[list, list]:
    """Reconcilia os responsáveis da tarefa com ``desired_user_ids``.

    Usa a coleção ORM (cascade delete-orphan) para manter ``task.assignees``
    consistente para serialização imediata. Retorna (adicionados, removidos)
    como listas ordenadas de user_id. O caller faz o commit.
    """
    desired = {int(uid) for uid in desired_user_ids if uid}
    current = {a.user_id: a for a in task.assignees}
    to_remove = sorted(set(current) - desired)
    to_add = sorted(desired - set(current))
    for uid in to_remove:
        task.assignees.remove(current[uid])
    for uid in to_add:
        task.assignees.append(TaskAssignee(user_id=uid))
    return to_add, to_remove


def _read_task_filter_values(source):
    from routes.orgao_scope import parse_apenas_orgao_flag

    return {
        "orgao_filter": (source.get("orgao") or source.get("area") or "").strip(),
        "apenas_orgao_filter": parse_apenas_orgao_flag(source.get("apenas_orgao")),
        "project_filter": (source.get("project") or "").strip(),
        "prioridade_filter": (source.get("prioridade") or "").strip(),
        "tipo_filter": (source.get("tipo") or "").strip(),
        "status_filter": (source.get("status") or "").strip(),
        "responsavel_filter": _normalize_person_name(source.get("responsavel") or ""),
        "search_filter": (source.get("search") or "").strip(),
    }


def _merge_task_filter_values(*values_list):
    merged = {
        "orgao_filter": "",
        "apenas_orgao_filter": False,
        "project_filter": "",
        "prioridade_filter": "",
        "tipo_filter": "",
        "status_filter": "",
        "responsavel_filter": "",
        "search_filter": "",
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
    ordered.extend(
        sorted(
            (value for value in present if value not in preferred_order),
            key=lambda item: item.casefold(),
        )
    )
    return ordered


def _ensure_filter_option(options, selected_value, label):
    if not selected_value:
        return
    if any(option["value"] == selected_value for option in options):
        return
    options.append({"value": selected_value, "label": label})


def _build_task_filter_options(tasks, selected_filters=None):
    selected_filters = selected_filters or {}

    prioridade_options = [
        {"value": value, "label": _task_prioridade_label(value)}
        for value in _ordered_task_filter_values(
            [task.prioridade for task in tasks if task.prioridade],
            TASK_PRIORIDADE_ORDER,
        )
    ]
    tipo_options = [
        {"value": value, "label": _task_tipo_label(value)}
        for value in _ordered_task_filter_values(
            [task.tipo_pedido for task in tasks if task.tipo_pedido],
            TASK_TIPO_ORDER,
        )
    ]
    status_options = [
        {"value": value, "label": _task_status_label(value)}
        for value in TASK_STATUS_ORDER
    ]

    responsavel_values = []
    for task in tasks:
        responsavel_values.extend(_split_responsavel_names(task.responsavel or ""))
    responsavel_options = [
        {"value": value, "label": value}
        for value in sorted(set(responsavel_values), key=lambda item: item.casefold())
    ]

    _ensure_filter_option(
        prioridade_options,
        selected_filters.get("prioridade_filter", ""),
        _task_prioridade_label(selected_filters.get("prioridade_filter", "")),
    )
    _ensure_filter_option(
        tipo_options,
        selected_filters.get("tipo_filter", ""),
        _task_tipo_label(selected_filters.get("tipo_filter", "")),
    )
    _ensure_filter_option(
        status_options,
        selected_filters.get("status_filter", ""),
        _task_status_label(selected_filters.get("status_filter", "")),
    )
    _ensure_filter_option(
        responsavel_options,
        selected_filters.get("responsavel_filter", ""),
        selected_filters.get("responsavel_filter", ""),
    )

    return {
        "prioridade_options": prioridade_options,
        "tipo_options": tipo_options,
        "status_options": status_options,
        "responsavel_options": responsavel_options,
    }


def _build_task_listing_url(
    endpoint,
    *,
    orgao_filter="",
    project_filter="",
    prioridade_filter="",
    tipo_filter="",
    status_filter="",
    responsavel_filter="",
    page=None,
    project_id=None,
):
    kwargs = {}
    if project_id is not None:
        kwargs["project_id"] = project_id
    if orgao_filter:
        kwargs["orgao"] = orgao_filter
    if project_filter:
        kwargs["project"] = project_filter
    if prioridade_filter:
        kwargs["prioridade"] = prioridade_filter
    if tipo_filter:
        kwargs["tipo"] = tipo_filter
    if status_filter:
        kwargs["status"] = status_filter
    if responsavel_filter:
        kwargs["responsavel"] = responsavel_filter
    if page is not None:
        kwargs["page"] = page
    return url_for(endpoint, **kwargs)


def _build_legacy_query_args():
    query_args = request.args.to_dict(flat=True)
    if query_args:
        return "?" + urlencode(query_args)
    return ""


def _task_active_target_url(task):
    if task and task.project_id:
        return url_for(
            "main.project_tasks", project_id=task.project_id, focus_task=task.id
        )
    if task:
        return url_for("main.list_tasks", focus_task=task.id)
    return url_for("main.list_tasks")


def _escape_like_pattern(value: str) -> str:
    """Escapa curingas de LIKE (\\, % e _) para busca por substring literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_visible_tasks_query(
    include_archived=False,
    project_filter="",
    prioridade_filter="",
    tipo_filter="",
    status_filter="",
    responsavel_filter="",
    search_filter="",
    include_relations=True,
    orgao_filter_id=None,
    apenas_orgao=False,
):
    from routes.orgao_scope import expand_orgao_filter_ids
    from services.authorization import project_visibility_criterion

    query = Task.query
    if include_relations:
        query = query.options(
            joinedload(Task.project),
            joinedload(Task.etapa),
            joinedload(Task.comments).joinedload(TaskComment.author),
            joinedload(Task.anexos),
        )

    query = query.outerjoin(Project, Task.project_id == Project.id)

    if not g.user.is_admin:
        query = query.filter(
            or_(
                and_(Task.project_id.isnot(None), project_visibility_criterion(g.user)),
                and_(Task.project_id.is_(None), Task.created_by_id == g.user.id),
            )
        )

    if orgao_filter_id is not None:
        subtree_ids = expand_orgao_filter_ids(
            orgao_filter_id, incluir_descendentes=not apenas_orgao
        )
        if subtree_ids:
            query = query.filter(
                Task.project_id.isnot(None), Project.orgao_id.in_(subtree_ids)
            )
        else:
            query = query.filter(db.false())

    if project_filter:
        if project_filter == "sem_projeto":
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

    if search_filter:
        search_pattern = f"%{_escape_like_pattern(search_filter)}%"
        query = query.filter(
            or_(
                Task.descricao.ilike(search_pattern, escape="\\"),
                Project.titulo.ilike(search_pattern, escape="\\"),
            )
        )

    if responsavel_filter:
        pattern = f"%{_escape_like_pattern(responsavel_filter)}%"
        # Pós-backfill (scripts/migrations/backfill_task_assignees.py) os
        # responsáveis vivem em task_assignee; o texto legado só guarda nomes
        # sem usuário correspondente — o filtro precisa cobrir as duas fontes.
        assignee_name_match = Task.assignees.any(
            TaskAssignee.user.has(User.name.ilike(pattern, escape="\\"))
        )
        query = query.filter(
            or_(Task.responsavel.ilike(pattern, escape="\\"), assignee_name_match)
        )

    query = query.filter(Task.is_archived.is_(bool(include_archived)))

    return query.order_by(
        Project.titulo.asc(),
        Task.ordem.asc(),
        Task.created_at.asc(),
        Task.id.asc(),
    )
