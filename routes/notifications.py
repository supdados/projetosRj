import re
from urllib.parse import urlparse
from typing import Any

from flask import Response, g, jsonify
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import Etapa, Project, Task, UserNotification, db
from routes.orgao_scope import user_can_access_project
from time_utils import iso_utc, utc_now

from .api.envelope import ok
from .api.negotiation import api_login_required
from .blueprint import main_bp
from .decorators import login_required
from .shared import format_local_time

PROJECT_TARGET_RE = re.compile(r"^/(?:project|projetos?)/(\d+)(?:$|/)")
TASK_TARGET_RE = re.compile(r"^/tarefas/(\d+)(?:$|/)")

TargetRef = tuple[str, int]


def _notification_target_ref(target_url: str | None) -> TargetRef | None:
    """Extrai ``("project"|"task", id)`` do ``target_url``; ``None`` se não reconhecido.

    Cobre ``/project/<id>``, ``/projeto/<id>[/tarefas]``, ``/projetos/<id>`` e
    ``/tarefas/<id>``. URL desconhecida mantém a notificação visível.
    """
    path = urlparse(target_url or "").path
    project_match = PROJECT_TARGET_RE.match(path)
    if project_match:
        return ("project", int(project_match.group(1)))
    task_match = TASK_TARGET_RE.match(path)
    if task_match:
        return ("task", int(task_match.group(1)))
    return None


def _project_ids_by_task(task_ids: set[int]) -> dict[int, int | None]:
    """Mapeia task_id → project_id em uma query (coalesce cobre legadas via etapa)."""
    if not task_ids:
        return {}
    rows = (
        db.session.query(Task.id, func.coalesce(Task.project_id, Etapa.project_id))
        .outerjoin(Etapa, Task.etapa_id == Etapa.id)
        .filter(Task.id.in_(task_ids))
        .all()
    )
    return {task_id: project_id for task_id, project_id in rows}


def _accessible_project_ids(project_ids: set[int]) -> set[int]:
    """Filtra em lote os projetos que ``g.user`` pode ver (área OU convite).

    Delegado a ``user_can_access_project``: os mapas de papel e de convite são
    cacheados em ``g`` por request, então o custo segue 1 query de closure + 1
    de membership por request, não por projeto.
    """
    if not project_ids or g.user is None:
        return set()
    projects = Project.query.filter(Project.id.in_(project_ids)).all()
    return {p.id for p in projects if user_can_access_project(g.user, p)}


def _can_show_notification(
    ref: TargetRef | None,
    accessible_project_ids: set[int],
    project_ids_by_task: dict[int, int | None],
) -> bool:
    if ref is None:
        return True
    kind, ref_id = ref
    if kind == "project":
        return ref_id in accessible_project_ids
    if ref_id not in project_ids_by_task:
        # Tarefa deletada: o snapshot histórico da notificação permanece visível.
        return True
    project_id = project_ids_by_task[ref_id]
    if project_id is None:
        return True
    return project_id in accessible_project_ids


def _filter_visible_notifications(
    notifications: list[UserNotification],
) -> list[UserNotification]:
    """Aplica o escopo de órgão resolvendo projeto/tarefa dos targets em lote.

    Prefetch em 2 queries (tasks e projects via ``in_``) para evitar N+1 ao
    iterar todas as notificações do usuário.
    """
    refs = [_notification_target_ref(n.target_url) for n in notifications]
    task_ids = {ref[1] for ref in refs if ref and ref[0] == "task"}
    project_ids_by_task = _project_ids_by_task(task_ids)
    project_ids = {ref[1] for ref in refs if ref and ref[0] == "project"}
    project_ids.update(pid for pid in project_ids_by_task.values() if pid is not None)
    accessible = _accessible_project_ids(project_ids)
    return [
        notification
        for notification, ref in zip(notifications, refs)
        if _can_show_notification(ref, accessible, project_ids_by_task)
    ]


def _visible_notifications_for_current_user() -> list[UserNotification]:
    """Notificações do usuário corrente, mais recentes primeiro, já filtradas.

    Reusa a MESMA query e o MESMO ``_filter_visible_notifications`` do dropdown
    legado (escopo de órgão server-side), para que SPA e legado nunca divirjam.
    """
    candidates = (
        UserNotification.query.filter(UserNotification.recipient_user_id == g.user.id)
        .options(joinedload(UserNotification.actor))
        .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .all()
    )
    return _filter_visible_notifications(candidates)


def _serialize_notification(notification: UserNotification) -> dict[str, Any]:
    """Serializa uma notificação para a SPA (``created_at`` em ISO 8601)."""
    actor = notification.actor
    created_at = notification.created_at
    return {
        "id": notification.id,
        "event_type": notification.event_type,
        "title": notification.title,
        "message": notification.message,
        "created_at": iso_utc(created_at),
        "actor_name": actor.name if actor else "",
        "is_unread": not bool(notification.is_read),
        "target_url": notification.target_url,
    }


@main_bp.route("/api/notificacoes", methods=["GET"])
@api_login_required
def api_notificacoes_list() -> Response | tuple[Response, int]:
    """Lista as notificações visíveis do usuário + ``unread_count`` (envelope).

    Diferente do dropdown legado (``POST`` que marca tudo lido), esta rota é
    SOMENTE leitura: não muta ``is_read``. A SPA decide quando marcar via
    ``POST /api/notificacoes/marcar-lidas``.

    Returns:
        ``ok({items: [...], unread_count})`` (200); 401 sem sessão.
    """
    visible = _visible_notifications_for_current_user()
    unread_count = sum(1 for n in visible if not n.is_read)
    items = [_serialize_notification(n) for n in visible[:20]]
    return ok({"items": items, "unread_count": unread_count})


@main_bp.route("/api/notificacoes/marcar-lidas", methods=["POST"])
@api_login_required
def api_notificacoes_marcar_lidas() -> Response | tuple[Response, int]:
    """Marca como lidas as notificações VISÍVEIS não lidas do usuário (envelope).

    Respeita o escopo: só marca as que ``_can_show_notification`` permite ver
    (mesma regra do dropdown legado). Devolve quantas passaram a lidas.

    Returns:
        ``ok({marked: int, unread_count: 0})`` (200); 401 sem sessão.
    """
    visible = _visible_notifications_for_current_user()
    unread_ids = [n.id for n in visible if not n.is_read]
    if not unread_ids:
        return ok({"marked": 0, "unread_count": 0})

    UserNotification.query.filter(
        UserNotification.recipient_user_id == g.user.id,
        UserNotification.id.in_(unread_ids),
        UserNotification.is_read.is_(False),
    ).update(
        {UserNotification.is_read: True, UserNotification.read_at: utc_now()},
        synchronize_session=False,
    )
    db.session.commit()
    return ok({"marked": len(unread_ids), "unread_count": 0})


@main_bp.route("/api/notificacoes/dropdown", methods=["POST"])
@login_required
def notifications_dropdown_api():
    base_query = UserNotification.query.filter(
        UserNotification.recipient_user_id == g.user.id
    )

    candidate_notifications = (
        base_query.options(joinedload(UserNotification.actor))
        .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .all()
    )
    visible_notifications = _filter_visible_notifications(candidate_notifications)
    notifications = visible_notifications[:20]
    visible_unread_ids = [
        notification.id
        for notification in visible_notifications
        if not notification.is_read
    ]
    unread_before = len(visible_unread_ids)
    unread_notification_ids = {
        notification.id for notification in notifications if not notification.is_read
    }

    if visible_unread_ids:
        UserNotification.query.filter(
            UserNotification.recipient_user_id == g.user.id,
            UserNotification.id.in_(visible_unread_ids),
            UserNotification.is_read.is_(False),
        ).update(
            {
                UserNotification.is_read: True,
                UserNotification.read_at: utc_now(),
            },
            synchronize_session=False,
        )
        db.session.commit()

    items = [
        {
            "id": notification.id,
            "event_type": notification.event_type,
            "title": notification.title,
            "message": notification.message,
            "actor_name": notification.actor.name if notification.actor else "",
            "target_url": notification.target_url,
            "created_at": format_local_time(notification.created_at, "%d/%m/%Y %H:%M"),
            "is_unread": notification.id in unread_notification_ids,
        }
        for notification in notifications
    ]

    return jsonify(
        {
            "items": items,
            "unread_before": unread_before,
            "unread_after": 0,
        }
    )
