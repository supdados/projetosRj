import datetime
import secrets
import uuid
from urllib.parse import urlparse

from flask import abort, current_app, g, request, url_for

from models import CalendarEvent, ProjectStageMeeting, UserCalendarConnection, db
from services.calendar_core import (
    TIMEZONE_BR,
    extract_meet_link,
    format_human_datetime,
    format_input_datetime,
    parse_event_form,
    parse_google_event_datetime,
)
from services.calendar_sync import (
    delete_remote_event,
    ensure_google_access_token,
    sync_local_event_to_google,
)
from services.google_calendar import (
    GoogleCalendarError,
    build_google_authorization_url,
    create_google_calendar_event,
    create_google_calendar_watch,
    delete_google_calendar_event,
    exchange_google_code_for_tokens,
    get_google_userinfo,
    get_google_client_redirect_uris,
    is_google_calendar_enabled,
    list_google_calendar_events,
    refresh_google_access_token,
    stop_google_calendar_watch,
    update_google_calendar_event,
)
from services.project_meetings import (
    _weekend_shift_message,
    can_manage_project_meeting,
    delete_local_calendar_event_mirrors,
    find_project_meeting_by_google_event,
    find_project_meeting_for_calendar_event,
    mark_project_meeting_sync_error,
    shift_weekend_calendar_event,
    sync_etapa_from_meeting,
    sync_local_calendar_event_mirrors,
    update_meeting_from_calendar_event,
)
from time_utils import utc_now

GOOGLE_AUTH_STATE_SESSION_KEY = "google_calendar_auth_state"
GOOGLE_AUTH_REDIRECT_SESSION_KEY = "google_calendar_auth_redirect_uri"
AUTO_SYNC_INTERVAL_SECONDS = 300
AUTO_WATCH_RENEW_BEFORE_SECONDS = 1800


def _resolve_runtime_google_redirect_uri():
    configured_redirect_uri = str(
        current_app.config.get("GOOGLE_CALENDAR_REDIRECT_URI", "")
    ).strip()
    if configured_redirect_uri:
        return configured_redirect_uri

    callback_path = url_for("main.google_calendar_oauth_callback")
    callback_url = _build_public_url(callback_path)
    if _configured_public_origin():
        return callback_url

    callback_parsed = urlparse(callback_url)
    redirect_uris = get_google_client_redirect_uris(current_app.config)

    if callback_url in redirect_uris:
        return callback_url

    request_host = _public_host_without_port()
    public_scheme = _public_scheme()
    for candidate in redirect_uris:
        parsed = urlparse(candidate)
        if (
            parsed.path == callback_parsed.path
            and parsed.hostname == request_host
            and parsed.scheme == public_scheme
        ):
            return candidate

    for candidate in redirect_uris:
        if urlparse(candidate).path == callback_parsed.path:
            return candidate

    return callback_url


def _resolve_google_calendar_id():
    configured = str(
        current_app.config.get("GOOGLE_CALENDAR_DEFAULT_ID", "primary")
    ).strip()
    return configured or "primary"


def _forwarded_header_value(header_name):
    raw_value = (request.headers.get(header_name) or "").strip()
    if not raw_value:
        return ""
    return raw_value.split(",", 1)[0].strip()


def _configured_public_origin():
    configured = str(
        current_app.config.get("GOOGLE_CALENDAR_PUBLIC_BASE_URL", "")
    ).strip()
    if not configured:
        return ""

    parsed = urlparse(configured)
    if not parsed.scheme or not parsed.netloc:
        current_app.logger.warning(
            "GOOGLE_CALENDAR_PUBLIC_BASE_URL inválida (%s). Use formato https://host.",
            configured,
        )
        return ""

    return f"{parsed.scheme}://{parsed.netloc}"


def _public_host():
    forwarded_host = _forwarded_header_value("X-Forwarded-Host")
    return forwarded_host or request.host


def _public_host_without_port():
    return _public_host().split(":", 1)[0]


def _public_scheme():
    forwarded_proto = _forwarded_header_value("X-Forwarded-Proto")
    if forwarded_proto:
        return forwarded_proto

    host = _public_host_without_port()
    # Mantém compatibilidade com desenvolvimento local via ngrok sem exigir env fixa.
    if host.endswith(".ngrok-free.dev") or host.endswith(".ngrok.app"):
        return "https"

    return request.scheme or "http"


def _build_public_url(path):
    normalized_path = path if str(path).startswith("/") else f"/{path}"
    configured_origin = _configured_public_origin()
    if configured_origin:
        return f"{configured_origin}{normalized_path}"
    return f"{_public_scheme()}://{_public_host()}{normalized_path}"


def _resolve_webhook_address():
    configured = str(current_app.config.get("GOOGLE_CALENDAR_WEBHOOK_URL", "")).strip()
    if configured:
        return configured
    return _build_public_url(url_for("main.calendar_webhook"))


def _describe_calendar_issue(error):
    if isinstance(error, GoogleCalendarError):
        body = error.response_body or ""
        if "webhookUrlNotHttps" in body or "WebHook callback must be HTTPS" in body:
            return (
                "Webhook do Google precisa ser HTTPS. Configure "
                "`GOOGLE_CALENDAR_WEBHOOK_URL` com `https://.../webhook` e recarregue a página."
            )
        if "invalid_grant" in body or "token has been expired or revoked" in body:
            return "invalid_grant"
        if error.status_code == 401:
            return "unauthorized"
    return str(error)


def _format_input_datetime(utc_naive):
    return format_input_datetime(utc_naive)


def _format_human_datetime(utc_naive):
    return format_human_datetime(utc_naive)


def _parse_event_form(form):
    return parse_event_form(form)


def _connection_for_current_user():
    if not g.user:
        return None
    return UserCalendarConnection.query.filter_by(user_id=g.user.id).first()


def _extract_meet_link(remote):
    return extract_meet_link(remote)


def _ensure_google_access_token(connection, *, force_refresh=False):
    return ensure_google_access_token(
        current_app.config,
        connection,
        force_refresh=force_refresh,
    )


def _sync_local_event_to_google(local_event, connection, *, create_conference=False):
    return sync_local_event_to_google(
        current_app.config,
        local_event,
        connection,
        create_conference=create_conference,
    )


def _refresh_connection_identity(connection, *, access_token=None):
    if connection is None:
        return None

    token = access_token or _ensure_google_access_token(connection)
    userinfo = get_google_userinfo(current_app.config, access_token=token)
    connection.google_account_id = (userinfo.get("sub") or "").strip() or None
    connection.google_account_email = (userinfo.get("email") or "").strip() or None
    return userinfo


def _user_can_edit_meeting_project(user, meeting):
    if (
        user is None
        or meeting is None
        or meeting.etapa is None
        or meeting.etapa.project is None
    ):
        return False

    from services.authorization import user_can_edit_project

    return user_can_edit_project(user, meeting.etapa.project)


def _sync_project_meeting_from_calendar_event(event, *, connection=None, user=None):
    meeting = find_project_meeting_for_calendar_event(event, connection=connection)
    if meeting is None:
        return None
    actor = user if user is not None else getattr(connection, "user", None)
    if not _user_can_edit_meeting_project(actor, meeting):
        return None

    _enforce_meeting_weekend_rule(event, meeting, connection)
    update_meeting_from_calendar_event(meeting, event)
    sync_etapa_from_meeting(meeting.etapa, meeting, title=event.title)
    sync_local_calendar_event_mirrors(meeting, title=event.title)
    return meeting


def _enforce_meeting_weekend_rule(event, meeting, connection) -> None:
    """Edição feita direto no Google pode cair em fim de semana; shift local +
    UM write-back corrige o Google. O eco do webhook já chega em dia útil,
    então o shift vira no-op e não há loop de sync.
    """
    weekend_shift = shift_weekend_calendar_event(event)
    if weekend_shift is None:
        return

    from routes.shared import log_project_action

    log_project_action(
        project_id=meeting.project_id,
        action_type="google_meeting_weekend_shift",
        description=_weekend_shift_message(weekend_shift),
        # Webhook do Google roda sem g.user; sem ator explícito não haveria auditoria.
        actor_user_id=_weekend_shift_actor_id(meeting, connection),
    )
    if connection is None:
        return
    try:
        _sync_local_event_to_google(event, connection)
    except Exception as exc:
        event.sync_status = "error"
        event.sync_error = str(exc)


def _weekend_shift_actor_id(meeting, connection) -> "int | None":
    connection_user_id = getattr(connection, "user_id", None)
    if connection_user_id is not None:
        return connection_user_id
    return getattr(meeting, "creator_user_id", None)


def _mark_project_meeting_removed_by_google(
    *,
    google_event_id,
    google_calendar_id=None,
    google_owner_account_id=None,
    user=None,
):
    meeting = find_project_meeting_by_google_event(
        google_event_id=google_event_id,
        google_calendar_id=google_calendar_id,
        google_owner_account_id=google_owner_account_id,
    )
    if meeting is None:
        return None
    actor = user if user is not None else None
    if not _user_can_edit_meeting_project(actor, meeting):
        return None

    delete_local_calendar_event_mirrors(meeting)
    mark_project_meeting_sync_error(
        meeting, message="Evento removido no Google Calendar."
    )
    sync_etapa_from_meeting(meeting.etapa, meeting, title=meeting.etapa.descricao)
    return meeting


def _delete_project_meeting(meeting):
    if meeting is None:
        return

    delete_local_calendar_event_mirrors(meeting)
    if meeting.etapa is not None:
        db.session.delete(meeting.etapa)
        return
    db.session.delete(meeting)


def _parse_google_event_datetime(payload):
    return parse_google_event_datetime(payload)


def _upsert_local_event_from_google(connection, item):
    google_event_id = item.get("id")
    if not google_event_id:
        return "ignored"

    existing = CalendarEvent.query.filter_by(
        user_id=connection.user_id,
        google_event_id=google_event_id,
    ).first()

    if item.get("status") == "cancelled":
        meeting = _mark_project_meeting_removed_by_google(
            google_event_id=google_event_id,
            google_calendar_id=connection.calendar_id or "primary",
            google_owner_account_id=connection.google_account_id,
            user=connection.user,
        )
        if existing is not None:
            db.session.delete(existing)
            return "deleted"
        if meeting is not None:
            return "deleted"
        return "ignored"

    starts_at, starts_all_day = _parse_google_event_datetime(item.get("start"))
    ends_at, ends_all_day = _parse_google_event_datetime(item.get("end"))
    is_all_day = bool(starts_all_day and ends_all_day)
    if starts_at is None or ends_at is None:
        return "ignored"

    if is_all_day and ends_at > starts_at:
        # Google envia all-day com fim exclusivo (00:00 do dia seguinte).
        # Internamente usamos fim inclusivo (23:59 do último dia).
        ends_at -= datetime.timedelta(minutes=1)
    elif ends_at <= starts_at:
        default_duration = (
            datetime.timedelta(minutes=1439)
            if is_all_day
            else datetime.timedelta(hours=1)
        )
        ends_at = starts_at + default_duration

    event = existing
    if event is None:
        event = CalendarEvent(
            user_id=connection.user_id,
            title=item.get("summary") or "(Sem título)",
            starts_at=starts_at,
            ends_at=ends_at,
        )
        db.session.add(event)

    event.title = item.get("summary") or "(Sem título)"
    event.description = item.get("description") or None
    event.location = item.get("location") or None
    event.starts_at = starts_at
    event.ends_at = ends_at
    event.is_all_day = is_all_day
    event.timezone = str((item.get("start") or {}).get("timeZone") or "UTC")
    event.source = "google"
    event.google_calendar_id = connection.calendar_id or "primary"
    event.google_event_id = google_event_id
    event.meet_link = _extract_meet_link(item)
    event.sync_status = "ok"
    event.sync_error = None
    event.last_synced_at = utc_now()
    _sync_project_meeting_from_calendar_event(
        event, connection=connection, user=connection.user
    )

    return "upserted"


def _sync_events_from_google(connection, *, force_full=False):
    calendar_id = connection.calendar_id or "primary"
    access_token = _ensure_google_access_token(connection)

    use_sync_token = bool(connection.sync_token and not force_full)
    summary = {
        "upserted": 0,
        "deleted": 0,
        "ignored": 0,
        "full_sync": False,
    }

    while True:
        params_base = {
            "singleEvents": "true",
            "showDeleted": "true",
            "maxResults": "250",
        }
        if use_sync_token:
            params_base["syncToken"] = connection.sync_token
        else:
            summary["full_sync"] = True
            time_min = (
                (
                    utc_now().replace(tzinfo=datetime.timezone.utc)
                    - datetime.timedelta(days=365)
                )
                .isoformat()
                .replace("+00:00", "Z")
            )
            params_base["timeMin"] = time_min

        next_sync_token = None
        page_token = None

        try:
            while True:
                params = dict(params_base)
                if page_token:
                    params["pageToken"] = page_token

                payload = list_google_calendar_events(
                    current_app.config,
                    access_token=access_token,
                    calendar_id=calendar_id,
                    params=params,
                )

                for item in payload.get("items") or []:
                    action = _upsert_local_event_from_google(connection, item)
                    if action == "upserted":
                        summary["upserted"] += 1
                    elif action == "deleted":
                        summary["deleted"] += 1
                    else:
                        summary["ignored"] += 1

                page_token = payload.get("nextPageToken")
                if not page_token:
                    next_sync_token = payload.get("nextSyncToken")
                    break

            if next_sync_token:
                connection.sync_token = next_sync_token
            connection.last_sync_at = utc_now()
            return summary
        except GoogleCalendarError as exc:
            if use_sync_token and exc.status_code == 410:
                connection.sync_token = None
                use_sync_token = False
                continue
            raise


def _stop_watch_channel(connection, *, suppress_errors):
    if not connection.watch_channel_id or not connection.watch_resource_id:
        connection.watch_channel_id = None
        connection.watch_resource_id = None
        connection.watch_expiration = None
        connection.watch_channel_token = None
        return

    try:
        access_token = _ensure_google_access_token(connection)
        stop_google_calendar_watch(
            current_app.config,
            access_token=access_token,
            channel_id=connection.watch_channel_id,
            resource_id=connection.watch_resource_id,
        )
    except Exception:
        if not suppress_errors:
            raise
    finally:
        connection.watch_channel_id = None
        connection.watch_resource_id = None
        connection.watch_expiration = None
        connection.watch_channel_token = None


def _renew_watch_channel(connection):
    _stop_watch_channel(connection, suppress_errors=True)

    access_token = _ensure_google_access_token(connection)
    channel_id = str(uuid.uuid4())
    channel_token = secrets.token_urlsafe(24)

    payload = create_google_calendar_watch(
        current_app.config,
        access_token=access_token,
        calendar_id=connection.calendar_id or "primary",
        channel_id=channel_id,
        webhook_address=_resolve_webhook_address(),
        channel_token=channel_token,
        ttl_seconds=int(
            current_app.config.get("GOOGLE_CALENDAR_WATCH_TTL_SECONDS", 604800)
        ),
    )

    expiration_raw = payload.get("expiration")
    watch_expiration = None
    if expiration_raw is not None:
        try:
            expiration_ms = int(expiration_raw)
            watch_expiration = datetime.datetime.fromtimestamp(
                expiration_ms / 1000, tz=datetime.timezone.utc
            ).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            watch_expiration = None

    connection.watch_channel_id = payload.get("id") or channel_id
    connection.watch_resource_id = payload.get("resourceId")
    connection.watch_expiration = watch_expiration
    connection.watch_channel_token = channel_token

    return {
        "channel_id": connection.watch_channel_id,
        "resource_id": connection.watch_resource_id,
        "expires_at": connection.watch_expiration,
    }


def _event_json(event):
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description or "",
        "location": event.location or "",
        "starts_at": _format_input_datetime(event.starts_at),
        "ends_at": _format_input_datetime(event.ends_at),
        "starts_at_display": _format_human_datetime(event.starts_at),
        "ends_at_display": _format_human_datetime(event.ends_at),
        "sync_status": event.sync_status,
        "source": event.source,
        "meet_link": event.meet_link or "",
        "is_all_day": bool(event.is_all_day),
    }


def _connection_for_webhook(channel_id):
    if not channel_id:
        return None
    return UserCalendarConnection.query.filter_by(watch_channel_id=channel_id).first()


def _auto_sync_interval_seconds():
    raw_value = current_app.config.get(
        "GOOGLE_CALENDAR_AUTO_SYNC_INTERVAL_SECONDS", AUTO_SYNC_INTERVAL_SECONDS
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return AUTO_SYNC_INTERVAL_SECONDS
    return max(30, value)


def _auto_watch_renew_before_seconds():
    raw_value = current_app.config.get(
        "GOOGLE_CALENDAR_AUTO_WATCH_RENEW_BEFORE_SECONDS",
        AUTO_WATCH_RENEW_BEFORE_SECONDS,
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return AUTO_WATCH_RENEW_BEFORE_SECONDS
    return max(60, value)


def _should_auto_renew_watch(connection, now_utc):
    if not connection.watch_channel_id or not connection.watch_resource_id:
        return True
    if not connection.watch_expiration:
        return True
    threshold = now_utc + datetime.timedelta(seconds=_auto_watch_renew_before_seconds())
    return connection.watch_expiration <= threshold


def _should_auto_sync(connection, now_utc):
    if connection.last_sync_at is None:
        return True
    threshold = now_utc - datetime.timedelta(seconds=_auto_sync_interval_seconds())
    return connection.last_sync_at <= threshold


_EXPIRED_TOKEN_CODES = {"invalid_grant", "unauthorized"}

_FRIENDLY_CALENDAR_ISSUES = {
    "invalid_grant": "Sua conexão com o Google Calendar expirou e foi removida. Conecte novamente para retomar a sincronização.",
    "unauthorized": "Sua conexão com o Google Calendar perdeu a autorização e foi removida. Conecte novamente para retomar a sincronização.",
}


def _auto_disconnect(connection):
    """Remove a conexão quando o token está expirado/revogado."""
    _stop_watch_channel(connection, suppress_errors=True)
    db.session.delete(connection)


def _run_auto_calendar_maintenance(connection):
    issues = []
    now_utc = utc_now()
    disconnected = False

    if _should_auto_renew_watch(connection, now_utc):
        try:
            _renew_watch_channel(connection)
        except Exception as exc:
            desc = _describe_calendar_issue(exc)
            if desc in _EXPIRED_TOKEN_CODES:
                _auto_disconnect(connection)
                disconnected = True
            issues.append(
                _FRIENDLY_CALENDAR_ISSUES.get(
                    desc,
                    "Não foi possível atualizar a conexão com o Google Calendar.",
                )
            )

    if not disconnected and _should_auto_sync(connection, now_utc):
        try:
            _sync_events_from_google(connection)
        except Exception as exc:
            desc = _describe_calendar_issue(exc)
            if desc in _EXPIRED_TOKEN_CODES:
                _auto_disconnect(connection)
                disconnected = True
            issues.append(
                _FRIENDLY_CALENDAR_ISSUES.get(
                    desc,
                    "Não foi possível sincronizar eventos com o Google Calendar.",
                )
            )

    return issues


def _get_user_event_or_404(event_id):
    event = CalendarEvent.query.filter_by(id=event_id, user_id=g.user.id).first()
    if event is None:
        abort(404)
    return event
