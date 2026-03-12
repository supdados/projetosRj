import datetime

from services.calendar_core import extract_meet_link, google_event_payload
from services.google_calendar import (
    GoogleCalendarError,
    create_google_calendar_event,
    delete_google_calendar_event,
    refresh_google_access_token,
    update_google_calendar_event,
)
from time_utils import utc_now


def ensure_google_access_token(config, connection, *, force_refresh=False):
    now = utc_now()
    if (
        not force_refresh
        and connection.access_token
        and connection.token_expires_at
        and connection.token_expires_at > (now + datetime.timedelta(seconds=60))
    ):
        return connection.access_token

    refreshed = refresh_google_access_token(
        config,
        refresh_token=connection.refresh_token,
    )
    connection.access_token = refreshed.get('access_token')

    expires_in = refreshed.get('expires_in')
    if expires_in is not None:
        try:
            seconds = max(int(expires_in), 0)
        except (TypeError, ValueError):
            seconds = 0
        connection.token_expires_at = now + datetime.timedelta(seconds=seconds)

    maybe_refresh = refreshed.get('refresh_token')
    if maybe_refresh:
        connection.refresh_token = maybe_refresh

    return connection.access_token


def sync_local_event_to_google(config, local_event, connection, *, create_conference=False):
    if connection is None:
        local_event.sync_status = 'pending'
        local_event.sync_error = 'Conexão com Google Calendar não configurada.'
        return None

    access_token = ensure_google_access_token(config, connection)
    payload = google_event_payload(local_event, create_conference=create_conference)
    calendar_id = connection.calendar_id or 'primary'
    conference_version = 1 if create_conference else 0

    if local_event.google_event_id:
        try:
            remote = update_google_calendar_event(
                config,
                access_token=access_token,
                calendar_id=calendar_id,
                event_id=local_event.google_event_id,
                event_payload=payload,
                conference_data_version=conference_version,
            )
        except GoogleCalendarError as exc:
            if exc.status_code == 404:
                remote = create_google_calendar_event(
                    config,
                    access_token=access_token,
                    calendar_id=calendar_id,
                    event_payload=payload,
                    conference_data_version=conference_version,
                )
            else:
                raise
    else:
        remote = create_google_calendar_event(
            config,
            access_token=access_token,
            calendar_id=calendar_id,
            event_payload=payload,
            conference_data_version=conference_version,
        )

    local_event.google_event_id = remote.get('id')
    local_event.google_calendar_id = calendar_id
    local_event.source = 'app'
    local_event.sync_status = 'ok'
    local_event.sync_error = None
    local_event.last_synced_at = utc_now()
    local_event.meet_link = extract_meet_link(remote)
    return remote


def delete_remote_event(config, connection, *, google_event_id, google_calendar_id=None):
    if connection is None or not google_event_id:
        return False

    access_token = ensure_google_access_token(config, connection)
    return delete_google_calendar_event(
        config,
        access_token=access_token,
        calendar_id=google_calendar_id or connection.calendar_id or 'primary',
        event_id=google_event_id,
    )
