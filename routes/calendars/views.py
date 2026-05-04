from flask import current_app, g, render_template

from models import CalendarEvent
from services.google_calendar import is_google_calendar_enabled

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.calendars.helpers import (
    _connection_for_current_user,
    _event_view_row,
    _event_json,
    _format_human_datetime,
)


@main_bp.route("/calendarios", methods=["GET"])
@login_required
def calendars_hub():
    connection = _connection_for_current_user()
    events = (
        CalendarEvent.query.filter_by(user_id=g.user.id)
        .order_by(CalendarEvent.starts_at.asc(), CalendarEvent.id.asc())
        .all()
    )
    event_rows = [_event_view_row(event) for event in events]

    return render_template(
        "calendars/calendars.html",
        calendar_events=event_rows,
        events_json=[_event_json(e) for e in events],
        connection=connection,
        google_calendar_enabled=is_google_calendar_enabled(current_app.config),
        last_sync_display=(
            _format_human_datetime(connection.last_sync_at)
            if connection and connection.last_sync_at
            else None
        ),
    )
