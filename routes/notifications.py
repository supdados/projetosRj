from flask import g, jsonify
from sqlalchemy.orm import joinedload

from models import UserNotification, db
from time_utils import utc_now

from .blueprint import main_bp
from .decorators import login_required
from .shared import format_local_time


@main_bp.route("/api/notificacoes/dropdown", methods=["POST"])
@login_required
def notifications_dropdown_api():
    base_query = UserNotification.query.filter(
        UserNotification.recipient_user_id == g.user.id
    )

    unread_before = base_query.filter(UserNotification.is_read.is_(False)).count()

    notifications = (
        base_query.options(joinedload(UserNotification.actor))
        .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .limit(20)
        .all()
    )
    unread_notification_ids = {
        notification.id for notification in notifications if not notification.is_read
    }

    if unread_before:
        base_query.filter(UserNotification.is_read.is_(False)).update(
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
