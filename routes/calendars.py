import datetime
import secrets
import uuid
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import abort, current_app, flash, g, redirect, render_template, request, session, url_for

from models import CalendarEvent, UserCalendarConnection, db
from services.google_calendar import (
    GoogleCalendarError,
    build_google_authorization_url,
    create_google_calendar_event,
    create_google_calendar_watch,
    delete_google_calendar_event,
    exchange_google_code_for_tokens,
    get_google_client_redirect_uris,
    is_google_calendar_enabled,
    list_google_calendar_events,
    refresh_google_access_token,
    stop_google_calendar_watch,
    update_google_calendar_event,
)
from time_utils import utc_now

from .blueprint import main_bp
from .decorators import login_required

TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')
GOOGLE_AUTH_STATE_SESSION_KEY = 'google_calendar_auth_state'
GOOGLE_AUTH_REDIRECT_SESSION_KEY = 'google_calendar_auth_redirect_uri'
AUTO_SYNC_INTERVAL_SECONDS = 300
AUTO_WATCH_RENEW_BEFORE_SECONDS = 1800


def _resolve_runtime_google_redirect_uri():
    configured_redirect_uri = str(current_app.config.get('GOOGLE_CALENDAR_REDIRECT_URI', '')).strip()
    if configured_redirect_uri:
        return configured_redirect_uri

    callback_path = url_for('main.google_calendar_oauth_callback')
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
        if parsed.path == callback_parsed.path and parsed.hostname == request_host and parsed.scheme == public_scheme:
            return candidate

    for candidate in redirect_uris:
        if urlparse(candidate).path == callback_parsed.path:
            return candidate

    return callback_url


def _resolve_google_calendar_id():
    configured = str(current_app.config.get('GOOGLE_CALENDAR_DEFAULT_ID', 'primary')).strip()
    return configured or 'primary'


def _forwarded_header_value(header_name):
    raw_value = (request.headers.get(header_name) or '').strip()
    if not raw_value:
        return ''
    return raw_value.split(',', 1)[0].strip()


def _configured_public_origin():
    configured = str(current_app.config.get('GOOGLE_CALENDAR_PUBLIC_BASE_URL', '')).strip()
    if not configured:
        return ''

    parsed = urlparse(configured)
    if not parsed.scheme or not parsed.netloc:
        current_app.logger.warning(
            'GOOGLE_CALENDAR_PUBLIC_BASE_URL inválida (%s). Use formato https://host.',
            configured,
        )
        return ''

    return f'{parsed.scheme}://{parsed.netloc}'


def _public_host():
    forwarded_host = _forwarded_header_value('X-Forwarded-Host')
    return forwarded_host or request.host


def _public_host_without_port():
    return _public_host().split(':', 1)[0]


def _public_scheme():
    forwarded_proto = _forwarded_header_value('X-Forwarded-Proto')
    if forwarded_proto:
        return forwarded_proto

    host = _public_host_without_port()
    # Mantém compatibilidade com desenvolvimento local via ngrok sem exigir env fixa.
    if host.endswith('.ngrok-free.dev') or host.endswith('.ngrok.app'):
        return 'https'

    return request.scheme or 'http'


def _build_public_url(path):
    normalized_path = path if str(path).startswith('/') else f'/{path}'
    configured_origin = _configured_public_origin()
    if configured_origin:
        return f'{configured_origin}{normalized_path}'
    return f'{_public_scheme()}://{_public_host()}{normalized_path}'


def _resolve_webhook_address():
    configured = str(current_app.config.get('GOOGLE_CALENDAR_WEBHOOK_URL', '')).strip()
    if configured:
        return configured
    return _build_public_url(url_for('main.calendar_webhook'))


def _describe_calendar_issue(error):
    if isinstance(error, GoogleCalendarError):
        body = (error.response_body or '')
        if (
            'webhookUrlNotHttps' in body
            or 'WebHook callback must be HTTPS' in body
        ):
            return (
                'Webhook do Google precisa ser HTTPS. Configure '
                '`GOOGLE_CALENDAR_WEBHOOK_URL` com `https://.../webhook` e recarregue a página.'
            )
    return str(error)


def _to_utc_naive(local_dt):
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=TIMEZONE_BR)
    return local_dt.astimezone(datetime.UTC).replace(tzinfo=None)


def _to_local_datetime(utc_naive):
    if utc_naive is None:
        return None
    aware = utc_naive.replace(tzinfo=datetime.UTC)
    return aware.astimezone(TIMEZONE_BR)


def _format_input_datetime(utc_naive):
    local = _to_local_datetime(utc_naive)
    if local is None:
        return ''
    return local.strftime('%Y-%m-%dT%H:%M')


def _format_human_datetime(utc_naive):
    local = _to_local_datetime(utc_naive)
    if local is None:
        return '-'
    return local.strftime('%d/%m/%Y %H:%M')


def _utc_naive_to_rfc3339(utc_naive):
    aware = utc_naive.replace(tzinfo=datetime.UTC)
    return aware.isoformat().replace('+00:00', 'Z')


def _parse_form_datetime(value):
    raw_value = (value or '').strip()
    if not raw_value:
        return None
    try:
        parsed = datetime.datetime.strptime(raw_value, '%Y-%m-%dT%H:%M')
    except ValueError as exc:
        raise ValueError('Formato de data/hora inválido. Use o seletor da página.') from exc
    return _to_utc_naive(parsed)


def _parse_event_form(form):
    title = (form.get('title') or '').strip()
    if not title:
        raise ValueError('Título do evento é obrigatório.')
    if len(title) > 200:
        raise ValueError('Título do evento deve ter no máximo 200 caracteres.')

    starts_at = _parse_form_datetime(form.get('starts_at'))
    ends_at = _parse_form_datetime(form.get('ends_at'))
    if starts_at is None or ends_at is None:
        raise ValueError('Data e hora de início/fim são obrigatórias.')
    if ends_at <= starts_at:
        raise ValueError('A data/hora de término precisa ser maior que a de início.')

    return {
        'title': title,
        'description': (form.get('description') or '').strip() or None,
        'location': (form.get('location') or '').strip() or None,
        'starts_at': starts_at,
        'ends_at': ends_at,
        'is_all_day': bool(form.get('all_day')),
        'create_conference': bool(form.get('create_conference')),
    }


def _connection_for_current_user():
    if not g.user:
        return None
    return UserCalendarConnection.query.filter_by(user_id=g.user.id).first()


def _extract_meet_link(remote):
    conference = remote.get('conferenceData') or {}
    for ep in (conference.get('entryPoints') or []):
        if ep.get('entryPointType') == 'video':
            return ep.get('uri') or None
    return remote.get('hangoutLink') or None


def _google_event_payload(local_event, *, create_conference=False):
    payload = {
        'summary': local_event.title,
        'description': local_event.description or '',
        'location': local_event.location or '',
        'start': {
            'dateTime': _utc_naive_to_rfc3339(local_event.starts_at),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': _utc_naive_to_rfc3339(local_event.ends_at),
            'timeZone': 'UTC',
        },
    }
    if create_conference:
        payload['conferenceData'] = {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
            }
        }
    return payload


def _ensure_google_access_token(connection, *, force_refresh=False):
    now = utc_now()
    if (
        not force_refresh
        and connection.access_token
        and connection.token_expires_at
        and connection.token_expires_at > (now + datetime.timedelta(seconds=60))
    ):
        return connection.access_token

    refreshed = refresh_google_access_token(
        current_app.config,
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


def _sync_local_event_to_google(local_event, connection, *, create_conference=False):
    if connection is None:
        local_event.sync_status = 'pending'
        local_event.sync_error = 'Conexão com Google Calendar não configurada.'
        return

    access_token = _ensure_google_access_token(connection)
    payload = _google_event_payload(local_event, create_conference=create_conference)
    calendar_id = connection.calendar_id or 'primary'
    conf_version = 1 if create_conference else 0

    if local_event.google_event_id:
        try:
            remote = update_google_calendar_event(
                current_app.config,
                access_token=access_token,
                calendar_id=calendar_id,
                event_id=local_event.google_event_id,
                event_payload=payload,
                conference_data_version=conf_version,
            )
        except GoogleCalendarError as exc:
            if exc.status_code == 404:
                remote = create_google_calendar_event(
                    current_app.config,
                    access_token=access_token,
                    calendar_id=calendar_id,
                    event_payload=payload,
                    conference_data_version=conf_version,
                )
            else:
                raise
    else:
        remote = create_google_calendar_event(
            current_app.config,
            access_token=access_token,
            calendar_id=calendar_id,
            event_payload=payload,
            conference_data_version=conf_version,
        )

    local_event.google_event_id = remote.get('id')
    local_event.google_calendar_id = calendar_id
    local_event.source = 'app'
    local_event.sync_status = 'ok'
    local_event.sync_error = None
    local_event.last_synced_at = utc_now()
    local_event.meet_link = _extract_meet_link(remote)


def _parse_google_event_datetime(payload):
    if not isinstance(payload, dict):
        return None, None

    raw_datetime = payload.get('dateTime')
    if raw_datetime:
        normalized = str(raw_datetime).replace('Z', '+00:00')
        dt = datetime.datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            timezone_name = str(payload.get('timeZone', 'UTC')).strip() or 'UTC'
            try:
                dt = dt.replace(tzinfo=ZoneInfo(timezone_name))
            except Exception:
                dt = dt.replace(tzinfo=datetime.UTC)
        return dt.astimezone(datetime.UTC).replace(tzinfo=None), False

    raw_date = payload.get('date')
    if raw_date:
        date_value = datetime.date.fromisoformat(str(raw_date))
        dt = datetime.datetime.combine(date_value, datetime.time.min, tzinfo=datetime.UTC)
        return dt.replace(tzinfo=None), True

    return None, None


def _upsert_local_event_from_google(connection, item):
    google_event_id = item.get('id')
    if not google_event_id:
        return 'ignored'

    existing = CalendarEvent.query.filter_by(
        user_id=connection.user_id,
        google_event_id=google_event_id,
    ).first()

    if item.get('status') == 'cancelled':
        if existing is not None:
            db.session.delete(existing)
            return 'deleted'
        return 'ignored'

    starts_at, starts_all_day = _parse_google_event_datetime(item.get('start'))
    ends_at, ends_all_day = _parse_google_event_datetime(item.get('end'))
    if starts_at is None or ends_at is None:
        return 'ignored'
    if ends_at <= starts_at:
        ends_at = starts_at + datetime.timedelta(hours=1)

    event = existing
    if event is None:
        event = CalendarEvent(
            user_id=connection.user_id,
            title=item.get('summary') or '(Sem título)',
            starts_at=starts_at,
            ends_at=ends_at,
        )
        db.session.add(event)

    event.title = item.get('summary') or '(Sem título)'
    event.description = item.get('description') or None
    event.location = item.get('location') or None
    event.starts_at = starts_at
    event.ends_at = ends_at
    event.is_all_day = bool(starts_all_day and ends_all_day)
    event.timezone = str((item.get('start') or {}).get('timeZone') or 'UTC')
    event.source = 'google'
    event.google_calendar_id = connection.calendar_id or 'primary'
    event.google_event_id = google_event_id
    event.meet_link = _extract_meet_link(item)
    event.sync_status = 'ok'
    event.sync_error = None
    event.last_synced_at = utc_now()

    return 'upserted'


def _sync_events_from_google(connection, *, force_full=False):
    calendar_id = connection.calendar_id or 'primary'
    access_token = _ensure_google_access_token(connection)

    use_sync_token = bool(connection.sync_token and not force_full)
    summary = {
        'upserted': 0,
        'deleted': 0,
        'ignored': 0,
        'full_sync': False,
    }

    while True:
        params_base = {
            'singleEvents': 'true',
            'showDeleted': 'true',
            'maxResults': '250',
        }
        if use_sync_token:
            params_base['syncToken'] = connection.sync_token
        else:
            summary['full_sync'] = True
            time_min = (
                utc_now().replace(tzinfo=datetime.UTC) - datetime.timedelta(days=365)
            ).isoformat().replace('+00:00', 'Z')
            params_base['timeMin'] = time_min

        next_sync_token = None
        page_token = None

        try:
            while True:
                params = dict(params_base)
                if page_token:
                    params['pageToken'] = page_token

                payload = list_google_calendar_events(
                    current_app.config,
                    access_token=access_token,
                    calendar_id=calendar_id,
                    params=params,
                )

                for item in payload.get('items') or []:
                    action = _upsert_local_event_from_google(connection, item)
                    if action == 'upserted':
                        summary['upserted'] += 1
                    elif action == 'deleted':
                        summary['deleted'] += 1
                    else:
                        summary['ignored'] += 1

                page_token = payload.get('nextPageToken')
                if not page_token:
                    next_sync_token = payload.get('nextSyncToken')
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
        calendar_id=connection.calendar_id or 'primary',
        channel_id=channel_id,
        webhook_address=_resolve_webhook_address(),
        channel_token=channel_token,
        ttl_seconds=int(current_app.config.get('GOOGLE_CALENDAR_WATCH_TTL_SECONDS', 604800)),
    )

    expiration_raw = payload.get('expiration')
    watch_expiration = None
    if expiration_raw is not None:
        try:
            expiration_ms = int(expiration_raw)
            watch_expiration = datetime.datetime.fromtimestamp(expiration_ms / 1000, tz=datetime.UTC).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            watch_expiration = None

    connection.watch_channel_id = payload.get('id') or channel_id
    connection.watch_resource_id = payload.get('resourceId')
    connection.watch_expiration = watch_expiration
    connection.watch_channel_token = channel_token

    return {
        'channel_id': connection.watch_channel_id,
        'resource_id': connection.watch_resource_id,
        'expires_at': connection.watch_expiration,
    }


def _event_view_row(event):
    return {
        'model': event,
        'starts_at_display': _format_human_datetime(event.starts_at),
        'ends_at_display': _format_human_datetime(event.ends_at),
        'starts_at_input': _format_input_datetime(event.starts_at),
        'ends_at_input': _format_input_datetime(event.ends_at),
    }


def _event_json(event):
    return {
        'id': event.id,
        'title': event.title,
        'description': event.description or '',
        'location': event.location or '',
        'starts_at': _format_input_datetime(event.starts_at),
        'ends_at': _format_input_datetime(event.ends_at),
        'starts_at_display': _format_human_datetime(event.starts_at),
        'ends_at_display': _format_human_datetime(event.ends_at),
        'sync_status': event.sync_status,
        'source': event.source,
        'meet_link': event.meet_link or '',
        'is_all_day': bool(event.is_all_day),
    }


def _connection_for_webhook(channel_id):
    if not channel_id:
        return None
    return UserCalendarConnection.query.filter_by(watch_channel_id=channel_id).first()


def _auto_sync_interval_seconds():
    raw_value = current_app.config.get('GOOGLE_CALENDAR_AUTO_SYNC_INTERVAL_SECONDS', AUTO_SYNC_INTERVAL_SECONDS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return AUTO_SYNC_INTERVAL_SECONDS
    return max(30, value)


def _auto_watch_renew_before_seconds():
    raw_value = current_app.config.get('GOOGLE_CALENDAR_AUTO_WATCH_RENEW_BEFORE_SECONDS', AUTO_WATCH_RENEW_BEFORE_SECONDS)
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


def _run_auto_calendar_maintenance(connection):
    issues = []
    now_utc = utc_now()

    if _should_auto_renew_watch(connection, now_utc):
        try:
            _renew_watch_channel(connection)
        except Exception as exc:
            issues.append(f'Falha na renovação automática do watch: {_describe_calendar_issue(exc)}')

    if _should_auto_sync(connection, now_utc):
        try:
            _sync_events_from_google(connection)
        except Exception as exc:
            issues.append(f'Falha na sincronização automática: {_describe_calendar_issue(exc)}')

    return issues


@main_bp.route('/calendarios', methods=['GET'])
@login_required
def calendars_hub():
    connection = _connection_for_current_user()
    auto_issues = []

    if connection is not None:
        auto_issues = _run_auto_calendar_maintenance(connection)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            auto_issues.append(f'Falha ao persistir manutenção automática: {exc}')

    for issue in auto_issues:
        flash(issue, 'warning')

    events = (
        CalendarEvent.query
        .filter_by(user_id=g.user.id)
        .order_by(CalendarEvent.starts_at.asc(), CalendarEvent.id.asc())
        .all()
    )
    event_rows = [_event_view_row(event) for event in events]

    return render_template(
        'calendars.html',
        calendar_events=event_rows,
        events_json=[_event_json(e) for e in events],
        connection=connection,
        google_calendar_enabled=is_google_calendar_enabled(current_app.config),
        last_sync_display=_format_human_datetime(connection.last_sync_at) if connection and connection.last_sync_at else None,
    )


@main_bp.route('/calendar/oauth/start', methods=['GET'])
@login_required
def start_google_calendar_oauth():
    if not is_google_calendar_enabled(current_app.config):
        flash('Integração Google Calendar indisponível. Verifique client_secret e variáveis de ambiente.', 'warning')
        return redirect(url_for('main.calendars_hub'))

    state = secrets.token_urlsafe(32)
    redirect_uri = _resolve_runtime_google_redirect_uri()
    session[GOOGLE_AUTH_STATE_SESSION_KEY] = state
    session[GOOGLE_AUTH_REDIRECT_SESSION_KEY] = redirect_uri

    try:
        authorization_url = build_google_authorization_url(
            current_app.config,
            state=state,
            redirect_uri=redirect_uri,
        )
    except GoogleCalendarError as exc:
        flash(f'Falha ao iniciar OAuth do Google Calendar: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    return redirect(authorization_url)


@main_bp.route('/calendar/oauth/callback', methods=['GET'])
@login_required
def google_calendar_oauth_callback():
    if not is_google_calendar_enabled(current_app.config):
        flash('Integração Google Calendar indisponível.', 'warning')
        return redirect(url_for('main.calendars_hub'))

    expected_state = session.pop(GOOGLE_AUTH_STATE_SESSION_KEY, None)
    redirect_uri = session.pop(GOOGLE_AUTH_REDIRECT_SESSION_KEY, None) or _resolve_runtime_google_redirect_uri()
    returned_state = request.args.get('state')
    auth_error = request.args.get('error')
    code = request.args.get('code')

    if auth_error:
        flash(f'Autorização Google não concluída: {auth_error}.', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if not expected_state or returned_state != expected_state:
        flash('Resposta OAuth do Google inválida (state divergente).', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if not code:
        flash('Resposta OAuth do Google sem código de autorização.', 'danger')
        return redirect(url_for('main.calendars_hub'))

    try:
        tokens = exchange_google_code_for_tokens(
            current_app.config,
            code=code,
            redirect_uri=redirect_uri,
        )
    except GoogleCalendarError as exc:
        flash(f'Falha ao trocar código OAuth por token: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    connection = _connection_for_current_user()
    if connection is None:
        connection = UserCalendarConnection(
            user_id=g.user.id,
            provider='google',
            calendar_id=_resolve_google_calendar_id(),
            refresh_token='',
        )
        db.session.add(connection)

    refresh_token = tokens.get('refresh_token') or connection.refresh_token
    if not refresh_token:
        flash(
            'Google não retornou refresh_token. Revogue o acesso no Google e tente novamente com consentimento.',
            'danger',
        )
        db.session.rollback()
        return redirect(url_for('main.calendars_hub'))

    connection.provider = 'google'
    connection.calendar_id = _resolve_google_calendar_id()
    connection.access_token = tokens.get('access_token')
    connection.refresh_token = refresh_token
    connection.scope = tokens.get('scope') or connection.scope

    expires_in = tokens.get('expires_in')
    if expires_in is not None:
        try:
            seconds = max(int(expires_in), 0)
        except (TypeError, ValueError):
            seconds = 0
        connection.token_expires_at = utc_now() + datetime.timedelta(seconds=seconds)

    sync_issue = None
    watch_issue = None

    try:
        _sync_events_from_google(connection, force_full=True)
    except GoogleCalendarError as exc:
        sync_issue = _describe_calendar_issue(exc)

    try:
        _renew_watch_channel(connection)
    except Exception as exc:
        watch_issue = _describe_calendar_issue(exc)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Falha ao salvar credenciais de calendário: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if sync_issue or watch_issue:
        flash('Conexão com Google Calendar concluída com alertas.', 'warning')
        if sync_issue:
            flash(f'Sincronização inicial não concluída: {sync_issue}', 'warning')
        if watch_issue:
            flash(f'Watch não ativado: {watch_issue}', 'warning')
    else:
        flash('Google Calendar conectado e sincronização ativa.', 'success')

    return redirect(url_for('main.calendars_hub'))


@main_bp.route('/calendarios/google/disconnect', methods=['POST'])
@login_required
def disconnect_google_calendar():
    connection = _connection_for_current_user()
    if connection is None:
        flash('Nenhuma conexão Google Calendar para desconectar.', 'info')
        return redirect(url_for('main.calendars_hub'))

    try:
        _stop_watch_channel(connection, suppress_errors=True)
        db.session.delete(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Falha ao desconectar Google Calendar: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    flash('Conexão Google Calendar removida.', 'success')
    return redirect(url_for('main.calendars_hub'))


@main_bp.route('/calendarios/google/sync', methods=['POST'])
@login_required
def sync_google_calendar_now():
    connection = _connection_for_current_user()
    if connection is None:
        flash('Conecte sua conta Google antes de sincronizar.', 'warning')
        return redirect(url_for('main.calendars_hub'))

    try:
        summary = _sync_events_from_google(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao sincronizar com Google Calendar: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    flash(
        (
            'Sincronização concluída: '
            f"{summary['upserted']} atualizado(s), "
            f"{summary['deleted']} removido(s), "
            f"{summary['ignored']} ignorado(s)."
        ),
        'success',
    )
    return redirect(url_for('main.calendars_hub'))


@main_bp.route('/calendarios/google/watch/renew', methods=['POST'])
@login_required
def renew_google_calendar_watch():
    connection = _connection_for_current_user()
    if connection is None:
        flash('Conecte sua conta Google antes de renovar watch.', 'warning')
        return redirect(url_for('main.calendars_hub'))

    try:
        watch_summary = _renew_watch_channel(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao renovar watch do Google Calendar: {_describe_calendar_issue(exc)}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if watch_summary.get('expires_at'):
        flash(
            f"Watch renovado até {_format_human_datetime(watch_summary['expires_at'])}.",
            'success',
        )
    else:
        flash('Watch renovado (sem data de expiração retornada pelo Google).', 'success')
    return redirect(url_for('main.calendars_hub'))


@main_bp.route('/calendarios/eventos', methods=['POST'])
@login_required
def create_calendar_event():
    try:
        payload = _parse_event_form(request.form)
    except ValueError as exc:
        flash(str(exc), 'warning')
        return redirect(url_for('main.calendars_hub'))

    event = CalendarEvent(
        user_id=g.user.id,
        title=payload['title'],
        description=payload['description'],
        location=payload['location'],
        starts_at=payload['starts_at'],
        ends_at=payload['ends_at'],
        is_all_day=payload['is_all_day'],
        timezone='America/Sao_Paulo',
        source='app',
    )
    db.session.add(event)

    connection = _connection_for_current_user()
    sync_warning = None
    if connection is not None:
        try:
            _sync_local_event_to_google(event, connection, create_conference=payload['create_conference'])
        except Exception as exc:
            event.sync_status = 'error'
            event.sync_error = str(exc)
            sync_warning = str(exc)
    else:
        event.sync_status = 'pending'
        event.sync_error = 'Evento salvo localmente. Conecte o Google Calendar para sincronizar.'

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao salvar evento: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if sync_warning:
        flash('Evento salvo localmente, mas falhou ao enviar para Google Calendar.', 'warning')
        flash(sync_warning, 'warning')
    elif connection is None:
        flash('Evento salvo localmente. Conecte o Google Calendar para sincronizar.', 'success')
    else:
        flash('Evento salvo e sincronizado com Google Calendar.', 'success')
    return redirect(url_for('main.calendars_hub'))


def _get_user_event_or_404(event_id):
    event = CalendarEvent.query.filter_by(id=event_id, user_id=g.user.id).first()
    if event is None:
        abort(404)
    return event


@main_bp.route('/calendarios/eventos/<int:event_id>/editar', methods=['POST'])
@login_required
def edit_calendar_event(event_id):
    event = _get_user_event_or_404(event_id)

    try:
        payload = _parse_event_form(request.form)
    except ValueError as exc:
        flash(str(exc), 'warning')
        return redirect(url_for('main.calendars_hub'))

    event.title = payload['title']
    event.description = payload['description']
    event.location = payload['location']
    event.starts_at = payload['starts_at']
    event.ends_at = payload['ends_at']
    event.is_all_day = payload['is_all_day']
    event.source = 'app'

    connection = _connection_for_current_user()
    sync_warning = None
    if connection is not None:
        try:
            _sync_local_event_to_google(event, connection, create_conference=payload['create_conference'])
        except Exception as exc:
            event.sync_status = 'error'
            event.sync_error = str(exc)
            sync_warning = str(exc)
    else:
        event.sync_status = 'pending'
        event.sync_error = 'Evento editado localmente. Conecte o Google Calendar para sincronizar.'

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao atualizar evento: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if sync_warning:
        flash('Evento atualizado localmente, mas falhou no sync com Google Calendar.', 'warning')
        flash(sync_warning, 'warning')
    elif connection is None:
        flash('Evento atualizado localmente.', 'success')
    else:
        flash('Evento atualizado e sincronizado com Google Calendar.', 'success')
    return redirect(url_for('main.calendars_hub'))


@main_bp.route('/calendarios/eventos/<int:event_id>/excluir', methods=['POST'])
@login_required
def delete_calendar_event(event_id):
    event = _get_user_event_or_404(event_id)
    connection = _connection_for_current_user()
    remote_warning = None

    if connection is not None and event.google_event_id:
        try:
            access_token = _ensure_google_access_token(connection)
            delete_google_calendar_event(
                current_app.config,
                access_token=access_token,
                calendar_id=connection.calendar_id or 'primary',
                event_id=event.google_event_id,
            )
        except Exception as exc:
            remote_warning = str(exc)

    db.session.delete(event)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao excluir evento: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if remote_warning:
        flash('Evento removido localmente, mas houve falha ao remover no Google Calendar.', 'warning')
        flash(remote_warning, 'warning')
    else:
        flash('Evento removido com sucesso.', 'success')
    return redirect(url_for('main.calendars_hub'))


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
        _sync_events_from_google(connection)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Falha ao processar webhook do Google Calendar.')
        return ('sync error', 500)

    return ('', 200)
