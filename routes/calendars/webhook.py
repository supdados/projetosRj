from flask import current_app, request

from models import db

from routes.blueprint import main_bp
import routes.calendars.helpers as _cal_helpers
from routes.calendars.helpers import (
    _connection_for_webhook,
)


@main_bp.route('/webhook', methods=['POST'])
def calendar_webhook():
    channel_id = request.headers.get('X-Goog-Channel-ID')
    if not channel_id:
        return ('missing channel id', 400)

    connection = _connection_for_webhook(channel_id)
    if connection is None:
        return ('', 204)

    resource_id = request.headers.get('X-Goog-Resource-ID')
    if connection.watch_resource_id and resource_id and resource_id != connection.watch_resource_id:
        return ('resource mismatch', 403)

    incoming_token = request.headers.get('X-Goog-Channel-Token')
    if connection.watch_channel_token and incoming_token != connection.watch_channel_token:
        return ('token mismatch', 403)

    resource_state = (request.headers.get('X-Goog-Resource-State') or '').strip().lower()
    if resource_state == 'sync':
        return ('', 200)

    try:
        _cal_helpers._sync_events_from_google(connection)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Falha ao processar webhook do Google Calendar.')
        return ('sync error', 500)

    return ('', 200)
