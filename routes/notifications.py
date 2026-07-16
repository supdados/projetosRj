import re
from urllib.parse import urlparse
from typing import Any

from flask import Response, g, jsonify
from sqlalchemy.orm import joinedload

from models import Project, UserNotification, db
from routes.orgao_scope import user_can_access_project
from time_utils import iso_utc, utc_now

from .api.envelope import fail, ok
from .api.negotiation import api_login_required
from .blueprint import main_bp
from .decorators import login_required
from .shared import format_local_time

PROJECT_TARGET_RE = re.compile(r"^/project/(\d+)(?:$|/|\?)")


def _project_id_from_notification_target(target_url):
    path = urlparse(target_url or "").path
    match = PROJECT_TARGET_RE.match(path)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _can_show_notification(notification):
    project_id = _project_id_from_notification_target(notification.target_url)
    if project_id is None:
        return True

    project = db.session.get(Project, project_id)
    return bool(project and user_can_access_project(g.user, project))


def _visible_notifications_for_current_user() -> list[UserNotification]:
    """Notificações do usuário corrente, mais recentes primeiro, já filtradas.

    Reusa a MESMA query e o MESMO ``_can_show_notification`` do dropdown legado
    (escopo de órgão server-side), para que SPA e legado nunca divirjam.
    """
    candidates = (
        UserNotification.query.filter(UserNotification.recipient_user_id == g.user.id)
        .options(joinedload(UserNotification.actor))
        .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .all()
    )
    return [n for n in candidates if _can_show_notification(n)]


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
    visible_notifications = [
        notification
        for notification in candidate_notifications
        if _can_show_notification(notification)
    ]
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
