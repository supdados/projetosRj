import datetime

import routes.etapas.meetings as etapa_meetings
from models import (
    CalendarEvent,
    Etapa,
    Project,
    ProjectHistory,
    ProjectStageMeeting,
    User,
    UserCalendarConnection,
    db,
)
from tests._orgao_helpers import link_user_to_orgao

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def _create_area_user(username, name, area):
    user = User(
        username=username,
        name=name,
        orgao="Orgao Teste",
        is_admin=False,
    )
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    link_user_to_orgao(user.id, area)
    return user


def _add_connection(user_id, account_id, email):
    connection = UserCalendarConnection(
        user_id=user_id,
        provider="google",
        calendar_id="primary",
        refresh_token=f"refresh-{user_id}",
        google_account_id=account_id,
        google_account_email=email,
    )
    db.session.add(connection)
    return connection


def _seed_project_meeting(
    seed_data, *, owner_user_id, owner_account_id, owner_email, sync_status="ok"
):
    starts_at = datetime.datetime(2026, 3, 20, 13, 0)
    ends_at = datetime.datetime(2026, 3, 20, 14, 0)
    event = CalendarEvent(
        user_id=owner_user_id,
        title="Reunião vinculada",
        starts_at=starts_at,
        ends_at=ends_at,
        source="app",
        google_event_id="google-linked-meeting-1",
        google_calendar_id="primary",
        sync_status=sync_status,
    )
    etapa = Etapa(
        descricao="Reunião vinculada",
        data_inicio=datetime.date(2026, 3, 20),
        data_fim=datetime.date(2026, 3, 20),
        responsavel=owner_email,
        project_id=seed_data["project_id"],
        ordem=40,
        entry_type="google_meeting",
    )
    db.session.add_all([event, etapa])
    db.session.flush()

    meeting = ProjectStageMeeting(
        etapa_id=etapa.id,
        project_id=seed_data["project_id"],
        calendar_event_id=event.id,
        creator_user_id=owner_user_id,
        google_owner_account_id=owner_account_id,
        google_owner_email=owner_email,
        google_event_id=event.google_event_id,
        google_calendar_id="primary",
        starts_at=starts_at,
        ends_at=ends_at,
        timezone="America/Sao_Paulo",
        sync_status=sync_status,
    )
    db.session.add(meeting)
    db.session.commit()
    return etapa.id


def test_add_project_meeting_ajax_success_creates_shared_stage_and_link(
    app, client_user, seed_data, monkeypatch
):
    with app.app_context():
        _add_connection(seed_data["user_id"], "google-shared-1", "user@example.com")
        db.session.commit()

    def fake_sync(_config, event, _connection, create_conference=False):
        event.google_event_id = "google-created-meeting-1"
        event.google_calendar_id = "primary"
        event.sync_status = "ok"
        event.sync_error = None
        event.meet_link = (
            "https://meet.google.com/aaa-bbbb-ccc" if create_conference else None
        )
        return event

    monkeypatch.setattr(etapa_meetings, "sync_local_event_to_google", fake_sync)

    response = client_user.post(
        f"/project/{seed_data['project_id']}/meeting/add",
        data={
            "title": "Kickoff do projeto",
            "starts_at": "2026-03-20T10:00",
            "ends_at": "2026-03-20T11:00",
            "location": "Sala 101",
            "description": "Alinhamento inicial",
            "create_conference": "on",
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["etapa"]["entry_type"] == "google_meeting"
    assert payload["etapa"]["meeting"]["can_manage"] is True
    assert payload["etapa"]["meeting"]["can_edit_dates"] is True
    assert payload["etapa"]["meeting"]["time_summary"] == "10:00 - 11:00"

    with app.app_context():
        etapa = db.session.get(Etapa, payload["etapa"]["id"])
        assert etapa is not None
        assert etapa.entry_type == "google_meeting"

        meeting = ProjectStageMeeting.query.filter_by(etapa_id=etapa.id).first()
        assert meeting is not None
        assert meeting.google_owner_account_id == "google-shared-1"
        assert meeting.meet_link == "https://meet.google.com/aaa-bbbb-ccc"

        event = db.session.get(CalendarEvent, meeting.calendar_event_id)
        assert event is not None
        assert event.google_event_id == "google-created-meeting-1"

        history = (
            ProjectHistory.query.filter_by(
                project_id=seed_data["project_id"], action_type="add_google_meeting"
            )
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None


def test_add_project_meeting_ajax_requires_google_identity(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/meeting/add",
        data={
            "title": "Reunião sem conexão",
            "starts_at": "2026-03-20T10:00",
            "ends_at": "2026-03-20T11:00",
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "google" in payload["message"].lower()


def test_same_google_account_on_another_internal_user_can_reschedule_project_meeting(
    app, client, seed_data, monkeypatch
):
    with app.app_context():
        _add_connection(seed_data["user_id"], "google-shared-1", "owner@example.com")
        shared_user = _create_area_user("shared_google", "Shared Google", "Auditoria")
        _add_connection(shared_user.id, "google-shared-1", "owner@example.com")
        meeting_etapa_id = _seed_project_meeting(
            seed_data,
            owner_user_id=seed_data["user_id"],
            owner_account_id="google-shared-1",
            owner_email="owner@example.com",
        )
        db.session.commit()
        shared_user_id = shared_user.id

    _login(client, shared_user_id)

    monkeypatch.setattr(
        etapa_meetings, "sync_local_event_to_google", lambda *_args, **_kwargs: _args[1]
    )

    response = client.post(
        f"/etapa/{meeting_etapa_id}/update_field",
        json={"field": "data_inicio", "value": "2026-03-21"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["isMeeting"] is True
    assert payload["newValue"] == "2026-03-21"
    assert payload["updatedEndDate"] == "2026-03-21"

    with app.app_context():
        etapa = db.session.get(Etapa, meeting_etapa_id)
        assert etapa.data_inicio == datetime.date(2026, 3, 21)
        assert etapa.data_fim == datetime.date(2026, 3, 21)


def test_same_google_account_can_edit_project_meeting_via_modal_route(
    app, client, seed_data, monkeypatch
):
    with app.app_context():
        _add_connection(seed_data["user_id"], "google-shared-1", "owner@example.com")
        shared_user = _create_area_user(
            "shared_google_editor", "Shared Editor", "Auditoria"
        )
        _add_connection(shared_user.id, "google-shared-1", "owner@example.com")
        meeting_etapa_id = _seed_project_meeting(
            seed_data,
            owner_user_id=seed_data["user_id"],
            owner_account_id="google-shared-1",
            owner_email="owner@example.com",
        )
        db.session.commit()
        shared_user_id = shared_user.id

    _login(client, shared_user_id)

    def fake_sync(_config, event, _connection, create_conference=False):
        event.sync_status = "ok"
        event.sync_error = None
        if create_conference:
            event.meet_link = "https://meet.google.com/edited-room"
        return event

    monkeypatch.setattr(etapa_meetings, "sync_local_event_to_google", fake_sync)

    response = client.post(
        f"/etapa/{meeting_etapa_id}/meeting/edit",
        data={
            "title": "Reunião editada",
            "starts_at": "2026-03-20T15:30",
            "ends_at": "2026-03-20T16:45",
            "location": "Sala nova",
            "description": "Pauta atualizada",
            "create_conference": "on",
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["etapa"]["descricao"] == "Reunião editada"
    assert payload["etapa"]["meeting"]["location"] == "Sala nova"
    assert payload["etapa"]["meeting"]["description"] == "Pauta atualizada"
    assert (
        payload["etapa"]["meeting"]["meet_link"]
        == "https://meet.google.com/edited-room"
    )

    with app.app_context():
        etapa = db.session.get(Etapa, meeting_etapa_id)
        assert etapa.descricao == "Reunião editada"
        assert etapa.data_inicio == datetime.date(2026, 3, 20)
        assert etapa.data_fim == datetime.date(2026, 3, 20)

        meeting = ProjectStageMeeting.query.filter_by(etapa_id=meeting_etapa_id).first()
        assert meeting is not None
        assert meeting.location == "Sala nova"
        assert meeting.description == "Pauta atualizada"
        assert meeting.meet_link == "https://meet.google.com/edited-room"

        event = db.session.get(CalendarEvent, meeting.calendar_event_id)
        assert event is not None
        assert event.title == "Reunião editada"
        assert event.location == "Sala nova"


def test_different_google_account_cannot_update_or_delete_project_meeting(
    app, client, seed_data
):
    with app.app_context():
        _add_connection(seed_data["user_id"], "google-shared-1", "owner@example.com")
        other_user = _create_area_user("other_google", "Other Google", "Auditoria")
        _add_connection(other_user.id, "google-other-1", "other@example.com")
        meeting_etapa_id = _seed_project_meeting(
            seed_data,
            owner_user_id=seed_data["user_id"],
            owner_account_id="google-shared-1",
            owner_email="owner@example.com",
        )
        db.session.commit()
        other_user_id = other_user.id

    _login(client, other_user_id)

    update_response = client.post(
        f"/etapa/{meeting_etapa_id}/update_field",
        json={"field": "data_inicio", "value": "2026-03-22"},
        headers=AJAX_HEADERS,
    )
    delete_response = client.post(
        f"/etapa/{meeting_etapa_id}/delete",
        headers=AJAX_HEADERS,
    )

    assert update_response.status_code == 403
    assert update_response.get_json()["success"] is False
    assert delete_response.status_code == 403
    assert delete_response.get_json()["success"] is False

    with app.app_context():
        assert db.session.get(Etapa, meeting_etapa_id) is not None


def test_google_meeting_does_not_block_project_conclusion(app, client_user, seed_data):
    with app.app_context():
        etapa = Etapa(
            descricao="Reunião informativa",
            data_inicio=datetime.date(2026, 3, 25),
            data_fim=datetime.date(2026, 3, 25),
            responsavel="owner@example.com",
            project_id=seed_data["project_complete_id"],
            ordem=10,
            entry_type="google_meeting",
        )
        event = CalendarEvent(
            user_id=seed_data["user_id"],
            title="Reunião informativa",
            starts_at=datetime.datetime(2026, 3, 25, 13, 0),
            ends_at=datetime.datetime(2026, 3, 25, 14, 0),
            source="app",
            google_event_id="google-conclude-1",
            google_calendar_id="primary",
            sync_status="ok",
        )
        db.session.add_all([etapa, event])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data["project_complete_id"],
                calendar_event_id=event.id,
                creator_user_id=seed_data["user_id"],
                google_owner_account_id="google-shared-1",
                google_owner_email="owner@example.com",
                google_event_id="google-conclude-1",
                google_calendar_id="primary",
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                timezone="America/Sao_Paulo",
                sync_status="ok",
            )
        )
        db.session.commit()

        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project.todas_etapas_concluidas is True
        assert project.total_workflow_etapas == 1

    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/concluir",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project.status == "Finalizado"
