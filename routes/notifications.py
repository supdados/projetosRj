import datetime

from flask import g, jsonify
from sqlalchemy.orm import joinedload

from models import UserNotification, db

from .blueprint import main_bp
from .decorators import login_required
from .shared import format_local_time


@main_bp.route('/api/notificacoes/dropdown', methods=['POST'])
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

    if unread_before:
        base_query.filter(UserNotification.is_read.is_(False)).update(
            {
                UserNotification.is_read: True,
                UserNotification.read_at: datetime.datetime.utcnow(),
            },
            synchronize_session=False,
        )
        db.session.commit()

    items = [
        {
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'actor_name': notification.actor.name if notification.actor else '',
            'target_url': notification.target_url,
            'created_at': format_local_time(notification.created_at, '%d/%m/%Y %H:%M'),
        }
        for notification in notifications
    ]

    return jsonify(
        {
            'items': items,
            'unread_before': unread_before,
            'unread_after': 0,
        }
    )
