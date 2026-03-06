import datetime

import routes.calendars as calendar_routes
from models import CalendarEvent, UserCalendarConnection, db
from services.google_calendar import GoogleCalendarError


def test_calendars_page_renders_core_actions(client_user):
    response = client_user.get('/calendarios')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'Gerencie eventos internos e sincronize com Google Calendar.' in html
    assert 'action="/calendarios/eventos"' in html
    assert 'href="/calendar/oauth/start"' in html


def test_create_calendar_event_without_google_connection_marks_pending(app, client_user, seed_data):
    response = client_user.post(
        '/calendarios/eventos',
        data={
            'title': 'Evento sem conexao',
            'location': 'Sala 2',
            'starts_at': '2026-03-22T09:00',
            'ends_at': '2026-03-22T10:00',
            'description': 'Evento local',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/calendarios')

    with app.app_context():
        event = (
            CalendarEvent.query
            .filter_by(user_id=seed_data['user_id'], title='Evento sem conexao')
            .order_by(CalendarEvent.id.desc())
            .first()
        )
        assert event is not None
        assert event.sync_status == 'pending'
        assert event.google_event_id is None


def test_google_calendar_oauth_callback_persists_refresh_token(app, client_user, seed_data, monkeypatch):
    app.config.update(
        GOOGLE_CALENDAR_ENABLED=True,
        GOOGLE_CALENDAR_REDIRECT_URI='http://localhost:5002/calendar/oauth/callback',
        GOOGLE_CALENDAR_DEFAULT_ID='primary',
    )

    monkeypatch.setattr(
        calendar_routes,
        'exchange_google_code_for_tokens',
        lambda _config, *, code, redirect_uri=None: {
            'access_token': f'access-{code}',
            'refresh_token': 'refresh-token-abc',
            'scope': 'https://www.googleapis.com/auth/calendar.events',
            'expires_in': 3600,
        },
    )
    monkeypatch.setattr(
        calendar_routes,
        '_sync_events_from_google',
        lambda connection, force_full=False: {'upserted': 0, 'deleted': 0, 'ignored': 0, 'full_sync': True},
    )

    def fake_renew_watch(connection):
        connection.watch_channel_id = 'channel-1'
        connection.watch_resource_id = 'resource-1'
        connection.watch_expiration = datetime.datetime(2026, 4, 1, 12, 0)
        return {'channel_id': 'channel-1', 'resource_id': 'resource-1', 'expires_at': connection.watch_expiration}

    monkeypatch.setattr(calendar_routes, '_renew_watch_channel', fake_renew_watch)

    with client_user.session_transaction() as session:
        session['google_calendar_auth_state'] = 'state-abc'
        session['google_calendar_auth_redirect_uri'] = 'http://localhost:5002/calendar/oauth/callback'

    response = client_user.get('/calendar/oauth/callback?code=ok&state=state-abc', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/calendarios')

    with app.app_context():
        connection = UserCalendarConnection.query.filter_by(user_id=seed_data['user_id']).first()
        assert connection is not None
        assert connection.refresh_token == 'refresh-token-abc'
        assert connection.access_token == 'access-ok'
        assert connection.calendar_id == 'primary'
        assert connection.watch_channel_id == 'channel-1'
        assert connection.watch_resource_id == 'resource-1'


def test_calendar_webhook_processes_known_channel(app, client, seed_data, monkeypatch):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data['user_id'],
            provider='google',
            calendar_id='primary',
            refresh_token='refresh-token',
            watch_channel_id='watch-1',
            watch_resource_id='resource-1',
            watch_channel_token='token-1',
        )
        db.session.add(connection)
        db.session.commit()

    calls = {'count': 0}

    def fake_sync(connection, force_full=False):
        calls['count'] += 1
        connection.last_sync_at = datetime.datetime(2026, 3, 6, 12, 0)
        return {'upserted': 0, 'deleted': 0, 'ignored': 0, 'full_sync': False}

    monkeypatch.setattr(calendar_routes, '_sync_events_from_google', fake_sync)

    response = client.post(
        '/webhook',
        headers={
            'X-Goog-Channel-ID': 'watch-1',
            'X-Goog-Resource-ID': 'resource-1',
            'X-Goog-Channel-Token': 'token-1',
            'X-Goog-Resource-State': 'exists',
        },
    )

    assert response.status_code == 200
    assert calls['count'] == 1


def test_calendar_webhook_rejects_invalid_channel_token(app, client, seed_data):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data['user_id'],
            provider='google',
            calendar_id='primary',
            refresh_token='refresh-token',
            watch_channel_id='watch-2',
            watch_resource_id='resource-2',
            watch_channel_token='token-right',
        )
        db.session.add(connection)
        db.session.commit()

    response = client.post(
        '/webhook',
        headers={
            'X-Goog-Channel-ID': 'watch-2',
            'X-Goog-Resource-ID': 'resource-2',
            'X-Goog-Channel-Token': 'token-wrong',
            'X-Goog-Resource-State': 'exists',
        },
    )

    assert response.status_code == 403


def test_resolve_webhook_address_prefers_forwarded_https_on_ngrok(app):
    app.config['GOOGLE_CALENDAR_WEBHOOK_URL'] = ''

    with app.test_request_context(
        '/calendarios',
        base_url='http://127.0.0.1:5002',
        headers={
            'X-Forwarded-Proto': 'https',
            'X-Forwarded-Host': 'reverberative-dawn-syndetically.ngrok-free.dev',
        },
    ):
        address = calendar_routes._resolve_webhook_address()

    assert address == 'https://reverberative-dawn-syndetically.ngrok-free.dev/webhook'


def test_describe_calendar_issue_normalizes_webhook_https_error():
    error = GoogleCalendarError(
        'bad request',
        status_code=400,
        response_body='{"error":{"errors":[{"reason":"push.webhookUrlNotHttps"}]}}',
    )

    message = calendar_routes._describe_calendar_issue(error)
    assert 'Webhook do Google precisa ser HTTPS' in message
