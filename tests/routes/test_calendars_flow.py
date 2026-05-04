import datetime

import routes.calendars.helpers as calendar_helpers
import routes.calendars.oauth as calendar_oauth
import routes.calendars.sync as calendar_sync
import routes.calendars.views as calendar_views
import routes.calendars.webhook as calendar_webhook
import routes.calendars.events as calendar_events
from models import CalendarEvent, Etapa, ProjectStageMeeting, UserCalendarConnection, db
from services.google_calendar import GoogleCalendarError


def test_calendars_page_renders_core_actions(client_user):
    response = client_user.get("/calendarios")
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert "Calendário" in html
    assert "Conectar" in html
    assert 'action="/calendarios/eventos"' in html
    assert 'href="/calendar/oauth/start"' in html
    assert 'id="fieldEndsAtDateCol"' in html


def test_calendars_connected_view_hides_calendar_watch_subtext(
    app, client_user, seed_data, monkeypatch
):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
        )
        db.session.add(connection)
        db.session.commit()

    response = client_user.get("/calendarios")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "cal-google-badge--on" in html
    assert "Desconectar" in html
    assert 'href="/calendar/oauth/start"' not in html
    assert "Calendário:" not in html
    assert "Watch expira em:" not in html
    assert "Renovar watch" not in html


def test_calendars_hub_does_not_run_auto_maintenance_on_get(
    app, client_user, seed_data, monkeypatch
):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
        )
        db.session.add(connection)
        db.session.commit()

    calls = {"count": 0}

    def fake_auto_maintenance(connection):
        calls["count"] += 1
        connection.last_sync_at = datetime.datetime(2026, 3, 6, 20, 0)
        return []

    monkeypatch.setattr(
        calendar_helpers, "_run_auto_calendar_maintenance", fake_auto_maintenance
    )

    response = client_user.get("/calendarios")
    assert response.status_code == 200
    assert calls["count"] == 0
    html = response.get_data(as_text=True)
    assert 'title="Sincronizar"' in html


def test_create_calendar_event_without_google_connection_marks_pending(
    app, client_user, seed_data
):
    response = client_user.post(
        "/calendarios/eventos",
        data={
            "title": "Evento sem conexao",
            "location": "Sala 2",
            "starts_at": "2026-03-22T09:00",
            "ends_at": "2026-03-22T10:00",
            "description": "Evento local",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/calendarios")

    with app.app_context():
        event = (
            CalendarEvent.query.filter_by(
                user_id=seed_data["user_id"], title="Evento sem conexao"
            )
            .order_by(CalendarEvent.id.desc())
            .first()
        )
        assert event is not None
        assert event.sync_status == "pending"
        assert event.google_event_id is None


def test_upsert_google_all_day_event_normalizes_exclusive_end(app, seed_data):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
        )
        db.session.add(connection)
        db.session.commit()

        action = calendar_helpers._upsert_local_event_from_google(
            connection,
            {
                "id": "google-all-day-1",
                "status": "confirmed",
                "summary": "Feriado",
                "start": {"date": "2026-03-22"},
                "end": {"date": "2026-03-23"},
            },
        )

        event = CalendarEvent.query.filter_by(
            user_id=seed_data["user_id"],
            google_event_id="google-all-day-1",
        ).first()

        assert action == "upserted"
        assert event is not None
        assert event.is_all_day is True
        assert (
            calendar_helpers._format_input_datetime(event.starts_at)
            == "2026-03-22T00:00"
        )
        assert (
            calendar_helpers._format_input_datetime(event.ends_at) == "2026-03-22T23:59"
        )


def test_google_calendar_oauth_callback_persists_refresh_token(
    app, client_user, seed_data, monkeypatch
):
    app.config.update(
        GOOGLE_CALENDAR_ENABLED=True,
        GOOGLE_CALENDAR_REDIRECT_URI="http://localhost:5002/calendar/oauth/callback",
        GOOGLE_CALENDAR_DEFAULT_ID="primary",
    )

    monkeypatch.setattr(
        calendar_oauth,
        "exchange_google_code_for_tokens",
        lambda _config, *, code, redirect_uri=None: {
            "access_token": f"access-{code}",
            "refresh_token": "refresh-token-abc",
            "scope": "https://www.googleapis.com/auth/calendar.events",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        calendar_helpers,
        "_sync_events_from_google",
        lambda connection, force_full=False: {
            "upserted": 0,
            "deleted": 0,
            "ignored": 0,
            "full_sync": True,
        },
    )
    monkeypatch.setattr(
        calendar_helpers,
        "get_google_userinfo",
        lambda _config, *, access_token: {
            "sub": "google-user-123",
            "email": "user@example.com",
        },
    )

    def fake_renew_watch(connection):
        connection.watch_channel_id = "channel-1"
        connection.watch_resource_id = "resource-1"
        connection.watch_expiration = datetime.datetime(2026, 4, 1, 12, 0)
        return {
            "channel_id": "channel-1",
            "resource_id": "resource-1",
            "expires_at": connection.watch_expiration,
        }

    monkeypatch.setattr(calendar_helpers, "_renew_watch_channel", fake_renew_watch)

    with client_user.session_transaction() as session:
        session["google_calendar_auth_state"] = "state-abc"
        session["google_calendar_auth_redirect_uri"] = (
            "http://localhost:5002/calendar/oauth/callback"
        )

    response = client_user.get(
        "/calendar/oauth/callback?code=ok&state=state-abc", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/calendarios")

    with app.app_context():
        connection = UserCalendarConnection.query.filter_by(
            user_id=seed_data["user_id"]
        ).first()
        assert connection is not None
        assert connection.refresh_token == "refresh-token-abc"
        assert connection.access_token == "access-ok"
        assert connection.calendar_id == "primary"
        assert connection.google_account_id == "google-user-123"
        assert connection.google_account_email == "user@example.com"
        assert connection.watch_channel_id == "channel-1"
        assert connection.watch_resource_id == "resource-1"


def test_calendar_webhook_processes_known_channel(app, client, seed_data, monkeypatch):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
            watch_channel_id="watch-1",
            watch_resource_id="resource-1",
            watch_channel_token="token-1",
        )
        db.session.add(connection)
        db.session.commit()

    calls = {"count": 0}

    def fake_sync(connection, force_full=False):
        calls["count"] += 1
        connection.last_sync_at = datetime.datetime(2026, 3, 6, 12, 0)
        return {"upserted": 0, "deleted": 0, "ignored": 0, "full_sync": False}

    monkeypatch.setattr(calendar_helpers, "_sync_events_from_google", fake_sync)

    response = client.post(
        "/webhook",
        headers={
            "X-Goog-Channel-ID": "watch-1",
            "X-Goog-Resource-ID": "resource-1",
            "X-Goog-Channel-Token": "token-1",
            "X-Goog-Resource-State": "exists",
        },
    )

    assert response.status_code == 200
    assert calls["count"] == 1


def test_calendar_webhook_rejects_invalid_channel_token(app, client, seed_data):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
            watch_channel_id="watch-2",
            watch_resource_id="resource-2",
            watch_channel_token="token-right",
        )
        db.session.add(connection)
        db.session.commit()

    response = client.post(
        "/webhook",
        headers={
            "X-Goog-Channel-ID": "watch-2",
            "X-Goog-Resource-ID": "resource-2",
            "X-Goog-Channel-Token": "token-wrong",
            "X-Goog-Resource-State": "exists",
        },
    )

    assert response.status_code == 403


def test_resolve_webhook_address_prefers_forwarded_https_on_ngrok(app):
    app.config["GOOGLE_CALENDAR_WEBHOOK_URL"] = ""
    app.config["GOOGLE_CALENDAR_PUBLIC_BASE_URL"] = ""

    with app.test_request_context(
        "/calendarios",
        base_url="http://127.0.0.1:5002",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "reverberative-dawn-syndetically.ngrok-free.dev",
        },
    ):
        address = calendar_helpers._resolve_webhook_address()

    assert address == "https://reverberative-dawn-syndetically.ngrok-free.dev/webhook"


def test_resolve_webhook_address_prefers_public_base_url_config(app):
    app.config["GOOGLE_CALENDAR_WEBHOOK_URL"] = ""
    app.config["GOOGLE_CALENDAR_PUBLIC_BASE_URL"] = "https://projetos.proderj.rj.gov.br"

    with app.test_request_context("/calendarios", base_url="http://127.0.0.1:5002"):
        address = calendar_helpers._resolve_webhook_address()

    assert address == "https://projetos.proderj.rj.gov.br/webhook"


def test_resolve_runtime_google_redirect_uri_prefers_public_base_url(app, monkeypatch):
    app.config["GOOGLE_CALENDAR_REDIRECT_URI"] = ""
    app.config["GOOGLE_CALENDAR_PUBLIC_BASE_URL"] = "https://projetos.proderj.rj.gov.br"

    monkeypatch.setattr(
        calendar_helpers,
        "get_google_client_redirect_uris",
        lambda _config: [
            "http://127.0.0.1:5002/calendar/oauth/callback",
            "https://projetos.proderj.rj.gov.br/calendar/oauth/callback",
        ],
    )

    with app.test_request_context("/calendarios", base_url="http://127.0.0.1:5002"):
        redirect_uri = calendar_helpers._resolve_runtime_google_redirect_uri()

    assert redirect_uri == "https://projetos.proderj.rj.gov.br/calendar/oauth/callback"


def test_resolve_runtime_google_redirect_uri_forces_public_base_url_when_configured(
    app, monkeypatch
):
    app.config["GOOGLE_CALENDAR_REDIRECT_URI"] = ""
    app.config["GOOGLE_CALENDAR_PUBLIC_BASE_URL"] = "https://projetos.proderj.rj.gov.br"

    monkeypatch.setattr(
        calendar_helpers,
        "get_google_client_redirect_uris",
        lambda _config: ["http://127.0.0.1:5002/calendar/oauth/callback"],
    )

    with app.test_request_context("/calendarios", base_url="http://127.0.0.1:5002"):
        redirect_uri = calendar_helpers._resolve_runtime_google_redirect_uri()

    assert redirect_uri == "https://projetos.proderj.rj.gov.br/calendar/oauth/callback"


def test_describe_calendar_issue_normalizes_webhook_https_error():
    error = GoogleCalendarError(
        "bad request",
        status_code=400,
        response_body='{"error":{"errors":[{"reason":"push.webhookUrlNotHttps"}]}}',
    )

    message = calendar_helpers._describe_calendar_issue(error)
    assert "Webhook do Google precisa ser HTTPS" in message


def test_edit_calendar_event_updates_linked_project_meeting(
    app, client_user, seed_data, monkeypatch
):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
            google_account_id="google-owner-1",
            google_account_email="user@example.com",
        )
        event = CalendarEvent(
            user_id=seed_data["user_id"],
            title="Reunião inicial",
            starts_at=datetime.datetime(2026, 3, 20, 13, 0),
            ends_at=datetime.datetime(2026, 3, 20, 14, 0),
            source="app",
            google_event_id="google-linked-calendar-edit",
            google_calendar_id="primary",
            sync_status="ok",
        )
        etapa = Etapa(
            descricao="Reunião inicial",
            data_inicio=datetime.date(2026, 3, 20),
            data_fim=datetime.date(2026, 3, 20),
            responsavel="user@example.com",
            project_id=seed_data["project_id"],
            ordem=50,
            entry_type="google_meeting",
        )
        db.session.add_all([connection, event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data["project_id"],
                calendar_event_id=event.id,
                creator_user_id=seed_data["user_id"],
                google_owner_account_id="google-owner-1",
                google_owner_email="user@example.com",
                google_event_id=event.google_event_id,
                google_calendar_id="primary",
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                timezone="America/Sao_Paulo",
                sync_status="ok",
            )
        )
        db.session.commit()
        event_id = event.id
        etapa_id = etapa.id

    monkeypatch.setattr(
        calendar_helpers,
        "_sync_local_event_to_google",
        lambda event, connection, create_conference=False: event,
    )

    response = client_user.post(
        f"/calendarios/eventos/{event_id}/editar",
        data={
            "title": "Reunião atualizada",
            "starts_at": "2026-03-21T10:00",
            "ends_at": "2026-03-21T11:00",
            "location": "Sala 202",
            "description": "Atualizada no calendário",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        etapa = db.session.get(Etapa, etapa_id)
        meeting = ProjectStageMeeting.query.filter_by(etapa_id=etapa_id).first()
        assert etapa.descricao == "Reunião atualizada"
        assert etapa.data_inicio == datetime.date(2026, 3, 21)
        assert etapa.data_fim == datetime.date(2026, 3, 21)
        assert meeting.location == "Sala 202"
        assert (
            calendar_helpers._format_human_datetime(meeting.starts_at)
            == "21/03/2026 10:00"
        )


def test_generate_meet_link_blocks_linked_project_meeting_owner_mismatch(
    app, client_user, seed_data, monkeypatch
):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
            google_account_id="google-current-account",
            google_account_email="current@example.com",
        )
        event = CalendarEvent(
            user_id=seed_data["user_id"],
            title="Reunião protegida",
            starts_at=datetime.datetime(2026, 3, 24, 13, 0),
            ends_at=datetime.datetime(2026, 3, 24, 14, 0),
            source="app",
            google_event_id="google-meet-owner-mismatch",
            google_calendar_id="primary",
            sync_status="ok",
        )
        etapa = Etapa(
            descricao="Reunião protegida",
            data_inicio=datetime.date(2026, 3, 24),
            data_fim=datetime.date(2026, 3, 24),
            responsavel="owner@example.com",
            project_id=seed_data["project_id"],
            ordem=70,
            entry_type="google_meeting",
        )
        db.session.add_all([connection, event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data["project_id"],
                calendar_event_id=event.id,
                creator_user_id=seed_data["user_id"],
                google_owner_account_id="google-original-owner",
                google_owner_email="owner@example.com",
                google_event_id=event.google_event_id,
                google_calendar_id="primary",
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                timezone="America/Sao_Paulo",
                sync_status="ok",
            )
        )
        db.session.commit()
        event_id = event.id

    calls = []

    def fake_sync(event, connection, create_conference=False):
        calls.append((event.id, create_conference))
        event.meet_link = "https://meet.google.com/blocked"
        return event

    monkeypatch.setattr(calendar_helpers, "_sync_local_event_to_google", fake_sync)

    response = client_user.post(
        f"/calendarios/eventos/{event_id}/gerar-meet",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert calls == []

    with app.app_context():
        event = db.session.get(CalendarEvent, event_id)
        assert event.meet_link is None


def test_generate_meet_link_updates_authorized_linked_project_meeting(
    app, client_user, seed_data, monkeypatch
):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
            google_account_id="google-owner-allowed",
            google_account_email="owner@example.com",
        )
        event = CalendarEvent(
            user_id=seed_data["user_id"],
            title="Reunião com Meet",
            starts_at=datetime.datetime(2026, 3, 25, 13, 0),
            ends_at=datetime.datetime(2026, 3, 25, 14, 0),
            source="app",
            google_event_id="google-meet-owner-allowed",
            google_calendar_id="primary",
            sync_status="ok",
        )
        etapa = Etapa(
            descricao="Reunião com Meet",
            data_inicio=datetime.date(2026, 3, 25),
            data_fim=datetime.date(2026, 3, 25),
            responsavel="owner@example.com",
            project_id=seed_data["project_id"],
            ordem=71,
            entry_type="google_meeting",
        )
        db.session.add_all([connection, event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data["project_id"],
                calendar_event_id=event.id,
                creator_user_id=seed_data["user_id"],
                google_owner_account_id="google-owner-allowed",
                google_owner_email="owner@example.com",
                google_event_id=event.google_event_id,
                google_calendar_id="primary",
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                timezone="America/Sao_Paulo",
                sync_status="ok",
            )
        )
        db.session.commit()
        event_id = event.id
        etapa_id = etapa.id

    def fake_sync(event, connection, create_conference=False):
        assert create_conference is True
        event.meet_link = "https://meet.google.com/allowed"
        event.sync_status = "ok"
        return event

    monkeypatch.setattr(calendar_helpers, "_sync_local_event_to_google", fake_sync)

    response = client_user.post(
        f"/calendarios/eventos/{event_id}/gerar-meet",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        event = db.session.get(CalendarEvent, event_id)
        meeting = ProjectStageMeeting.query.filter_by(etapa_id=etapa_id).first()
        assert event.meet_link == "https://meet.google.com/allowed"
        assert meeting.meet_link == "https://meet.google.com/allowed"


def test_upsert_google_cancelled_event_marks_linked_project_meeting_as_error(
    app, seed_data
):
    with app.app_context():
        connection = UserCalendarConnection(
            user_id=seed_data["user_id"],
            provider="google",
            calendar_id="primary",
            refresh_token="refresh-token",
            google_account_id="google-owner-1",
            google_account_email="user@example.com",
        )
        event = CalendarEvent(
            user_id=seed_data["user_id"],
            title="Reunião cancelada",
            starts_at=datetime.datetime(2026, 3, 22, 13, 0),
            ends_at=datetime.datetime(2026, 3, 22, 14, 0),
            source="google",
            google_event_id="google-cancelled-linked",
            google_calendar_id="primary",
            sync_status="ok",
        )
        etapa = Etapa(
            descricao="Reunião cancelada",
            data_inicio=datetime.date(2026, 3, 22),
            data_fim=datetime.date(2026, 3, 22),
            responsavel="user@example.com",
            project_id=seed_data["project_id"],
            ordem=60,
            entry_type="google_meeting",
        )
        db.session.add_all([connection, event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data["project_id"],
                calendar_event_id=event.id,
                creator_user_id=seed_data["user_id"],
                google_owner_account_id="google-owner-1",
                google_owner_email="user@example.com",
                google_event_id="google-cancelled-linked",
                google_calendar_id="primary",
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                timezone="America/Sao_Paulo",
                sync_status="ok",
            )
        )
        db.session.commit()
        etapa_id = etapa.id

        action = calendar_helpers._upsert_local_event_from_google(
            connection,
            {
                "id": "google-cancelled-linked",
                "status": "cancelled",
            },
        )

        assert action == "deleted"

        etapa = db.session.get(Etapa, etapa_id)
        meeting = ProjectStageMeeting.query.filter_by(etapa_id=etapa_id).first()
        assert etapa is not None
        assert meeting is not None
        assert meeting.sync_status == "error"
        assert "removido" in (meeting.sync_error or "").lower()
        assert (
            CalendarEvent.query.filter_by(
                google_event_id="google-cancelled-linked"
            ).count()
            == 0
        )
