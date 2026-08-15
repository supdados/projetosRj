"""Snapshot das CHAVES do payload de etapa (card / detalhe / reunião).

Regressão do item 3.4 (serializador único de etapa): as rotas de reunião
deixaram de usar o serializer legado ``_serialize_etapa_payload`` e passaram a
devolver o MESMO shape do detalhe (``routes/api/etapa_payload.py``). Se alguém
reintroduzir um shape paralelo, estas asserções quebram.
"""

import datetime
import time

import services.project_meetings as project_meetings
from models import (
    CalendarEvent,
    Etapa,
    ProjectStageMeeting,
    UserCalendarConnection,
    db,
)
from routes.api.serializers import serialize_etapa_card, serialize_etapa_detail

CARD_KEYS = {
    "id",
    "descricao",
    "data_inicio",
    "data_fim",
    "responsavel",
    "tem_responsavel",
    "ordem",
    "iniciada",
    "done",
    "project_id",
    "entry_type",
}

DETAIL_KEYS = {
    "id",
    "descricao",
    "data_inicio",
    "data_fim",
    "responsavel",
    "responsaveis",
    "ordem",
    "iniciada",
    "done",
    "comentarios",
    "project_id",
    "entry_type",
    "is_google_meeting",
    "task_count",
}

MEETING_BLOCK_KEYS = {
    "time_summary",
    "title",
    "description",
    "starts_at",
    "ends_at",
    "start_time_display",
    "end_time_display",
    "is_all_day",
    "sync_status",
    "sync_error",
    "location",
    "meet_link",
    "owner_email",
    "can_manage",
    "can_edit",
    "can_edit_dates",
}

AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}


def fake_google_sync(_config, event, _connection, create_conference=False):
    """Fake nomeado do sync com o Google (nenhuma chamada de rede nos testes)."""
    event.sync_status = "ok"
    event.sync_error = None
    if create_conference:
        event.meet_link = "https://meet.google.com/aaa-bbbb-ccc"
    return event


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()


def _seed_meeting_etapa(app, seed_data):
    """Cria etapa-reunião Google + conexão do usuário do seed; devolve o id."""
    with app.app_context():
        db.session.add(
            UserCalendarConnection(
                user_id=seed_data["user_id"],
                provider="google",
                calendar_id="primary",
                refresh_token="refresh-shape",
                google_account_id="google-shape-1",
                google_account_email="owner@example.com",
            )
        )
        starts_at = datetime.datetime(2026, 3, 20, 13, 0)
        ends_at = datetime.datetime(2026, 3, 20, 14, 0)
        event = CalendarEvent(
            user_id=seed_data["user_id"],
            title="Reunião de shape",
            starts_at=starts_at,
            ends_at=ends_at,
            source="app",
            google_event_id="google-shape-event-1",
            google_calendar_id="primary",
            sync_status="ok",
        )
        etapa = Etapa(
            descricao="Reunião de shape",
            data_inicio=datetime.date(2026, 3, 20),
            data_fim=datetime.date(2026, 3, 20),
            project_id=seed_data["project_id"],
            ordem=50,
            entry_type="google_meeting",
        )
        db.session.add_all([event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data["project_id"],
                calendar_event_id=event.id,
                creator_user_id=seed_data["user_id"],
                google_owner_account_id="google-shape-1",
                google_owner_email="owner@example.com",
                google_event_id=event.google_event_id,
                google_calendar_id="primary",
                starts_at=starts_at,
                ends_at=ends_at,
                timezone="America/Sao_Paulo",
                sync_status="ok",
            )
        )
        db.session.commit()
        return etapa.id


def test_card_and_detail_key_snapshot(app, seed_data):
    """Os dois serializers canônicos mantêm exatamente as chaves esperadas."""
    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_id"])
        assert set(serialize_etapa_card(etapa)) == CARD_KEYS
        assert set(serialize_etapa_detail(etapa)) == DETAIL_KEYS


def test_detail_endpoint_uses_canonical_etapa_keys(client_user, seed_data):
    """GET /detalhe: etapa comum sem bloco ``meeting``."""
    response = client_user.get(f"/api/projetos/{seed_data['project_id']}/detalhe")

    assert response.status_code == 200
    etapa = response.get_json()["data"]["etapas"][0]
    assert set(etapa) == DETAIL_KEYS


def test_meeting_api_response_matches_detail_shape(app, client, seed_data, monkeypatch):
    """POST /api/etapas/<id>/reuniao devolve o shape canônico + ``meeting``."""
    etapa_id = _seed_meeting_etapa(app, seed_data)
    monkeypatch.setattr(
        project_meetings, "sync_local_event_to_google", fake_google_sync
    )
    _login(client, seed_data["user_id"])

    response = client.post(
        f"/api/etapas/{etapa_id}/reuniao",
        json={
            "title": "Reunião editada",
            "starts_at": "2026-03-23T13:00",
            "ends_at": "2026-03-23T14:00",
        },
    )

    assert response.status_code == 200
    etapa = response.get_json()["data"]["etapa"]
    assert set(etapa) == DETAIL_KEYS | {"meeting"}
    assert set(etapa["meeting"]) == MEETING_BLOCK_KEYS
    assert etapa["is_google_meeting"] is True
    assert set(etapa["task_count"]) == {"total", "done"}


def test_legacy_meeting_ajax_response_matches_detail_shape(
    app, client, seed_data, monkeypatch
):
    """A rota Jinja legada de editar reunião devolve o MESMO shape da API."""
    etapa_id = _seed_meeting_etapa(app, seed_data)
    monkeypatch.setattr(
        project_meetings, "sync_local_event_to_google", fake_google_sync
    )
    _login(client, seed_data["user_id"])

    response = client.post(
        f"/etapa/{etapa_id}/meeting/edit",
        data={
            "title": "Reunião editada",
            "starts_at": "2026-03-23T13:00",
            "ends_at": "2026-03-23T14:00",
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    etapa = response.get_json()["etapa"]
    assert set(etapa) == DETAIL_KEYS | {"meeting"}
    assert set(etapa["meeting"]) == MEETING_BLOCK_KEYS
