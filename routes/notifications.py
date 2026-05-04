import re
from urllib.parse import urlparse

from flask import g, jsonify
from sqlalchemy.orm import joinedload

from models import Project, UserNotification, db
from routes.orgao_scope import user_can_access_project
from time_utils import utc_now

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
