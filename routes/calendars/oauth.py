import secrets

from flask import current_app, flash, g, redirect, request, session, url_for

from models import UserCalendarConnection, db
from services.google_calendar import (
    GoogleCalendarError,
    build_google_authorization_url,
    exchange_google_code_for_tokens,
    is_google_calendar_enabled,
)
from time_utils import utc_now
import datetime

from routes.blueprint import main_bp
from routes.decorators import login_required
import routes.calendars.helpers as _cal_helpers
from routes.calendars.helpers import (
    GOOGLE_AUTH_STATE_SESSION_KEY,
    GOOGLE_AUTH_REDIRECT_SESSION_KEY,
    _resolve_runtime_google_redirect_uri,
    _resolve_google_calendar_id,
    _connection_for_current_user,
    _describe_calendar_issue,
    _refresh_connection_identity,
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
    identity_issue = None

    try:
        _refresh_connection_identity(connection, access_token=connection.access_token)
    except Exception as exc:
        identity_issue = _describe_calendar_issue(exc)

    try:
        _cal_helpers._sync_events_from_google(connection, force_full=True)
    except GoogleCalendarError as exc:
        sync_issue = _describe_calendar_issue(exc)

    try:
        _cal_helpers._renew_watch_channel(connection)
    except Exception as exc:
        watch_issue = _describe_calendar_issue(exc)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Falha ao salvar credenciais de calendário: {exc}', 'danger')
        return redirect(url_for('main.calendars_hub'))

    if sync_issue or watch_issue or identity_issue:
        flash('Conexão com Google Calendar concluída com alertas.', 'warning')
        if identity_issue:
            flash(f'Conta Google conectada sem identificação completa: {identity_issue}', 'warning')
        if sync_issue:
            flash(f'Sincronização inicial não concluída: {sync_issue}', 'warning')
        if watch_issue:
            flash(f'Watch não ativado: {watch_issue}', 'warning')
    else:
        flash('Google Calendar conectado e sincronização ativa.', 'success')

    return redirect(url_for('main.calendars_hub'))
