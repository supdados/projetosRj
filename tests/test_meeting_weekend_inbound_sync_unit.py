"""Regressão do bug 2.12 (auditoria 2026-07-17): editar a reunião direto no
Google Calendar burlava o invariante "reunião nunca cai em fim de semana".

Cobre o caminho inbound (webhook/sync Google→app):
  * services.project_meetings.shift_weekend_calendar_event
  * routes.calendars.helpers._enforce_meeting_weekend_rule
    (shift local + UM write-back explícito, sem loop de eco)
"""

import datetime
from types import SimpleNamespace

import routes.shared
from models import ProjectHistory, db
from routes.calendars import helpers as cal_helpers
from services.calendar_core import to_local_datetime, to_utc_naive
from services.project_meetings import (
    shift_weekend_calendar_event,
    sync_etapa_from_meeting,
    update_meeting_from_calendar_event,
)


class FakeGooglePushRecorder:
    """Substitui _sync_local_event_to_google; registra cada write-back."""

    def __init__(self):
        self.pushed_events = []

    def __call__(self, event, connection, *, create_conference=False):
        self.pushed_events.append((event.starts_at, event.ends_at))


class FakeGooglePushFailure:
    """Substitui _sync_local_event_to_google; simula Google fora do ar."""

    def __call__(self, event, connection, *, create_conference=False):
        raise RuntimeError("google indisponível")


class FakeProjectActionLog:
    """Substitui routes.shared.log_project_action; registra entradas."""

    def __init__(self):
        self.entries = []

    def __call__(
        self,
        project_id,
        action_type,
        description,
        old_value=None,
        new_value=None,
        actor_user_id=None,
    ):
        self.entries.append((project_id, action_type, description, actor_user_id))


def _inbound_event(start_local, end_local):
    return SimpleNamespace(
        id=1,
        google_event_id="gid-1",
        google_calendar_id="primary",
        title="Reunião de etapa",
        description=None,
        location=None,
        starts_at=to_utc_naive(start_local),
        ends_at=to_utc_naive(end_local),
        is_all_day=False,
        timezone="America/Sao_Paulo",
        meet_link=None,
        sync_status="ok",
        sync_error=None,
    )


def _saturday_event():
    return _inbound_event(
        datetime.datetime(2026, 7, 18, 14, 0),  # sábado
        datetime.datetime(2026, 7, 18, 15, 0),
    )


def _meeting_stub():
    return SimpleNamespace(
        project_id=42, creator_user_id=7, timezone="America/Sao_Paulo"
    )


def _patch_collaborators(monkeypatch, push):
    action_log = FakeProjectActionLog()
    monkeypatch.setattr(routes.shared, "log_project_action", action_log)
    monkeypatch.setattr(cal_helpers, "_sync_local_event_to_google", push)
    return action_log


def test_shift_weekend_calendar_event_moves_saturday_event_to_monday():
    event = _saturday_event()

    shift = shift_weekend_calendar_event(event)

    assert shift == (datetime.date(2026, 7, 18), datetime.date(2026, 7, 20))
    start_local = to_local_datetime(event.starts_at)
    assert start_local.date() == datetime.date(2026, 7, 20)
    assert start_local.hour == 14
    assert (event.ends_at - event.starts_at) == datetime.timedelta(hours=1)


def test_shift_weekend_calendar_event_noop_on_business_day():
    event = _inbound_event(
        datetime.datetime(2026, 7, 20, 9, 0),  # segunda
        datetime.datetime(2026, 7, 20, 10, 0),
    )
    original = (event.starts_at, event.ends_at)

    assert shift_weekend_calendar_event(event) is None
    assert (event.starts_at, event.ends_at) == original


def test_inbound_weekend_event_shifts_and_writes_back_once(monkeypatch):
    push = FakeGooglePushRecorder()
    action_log = _patch_collaborators(monkeypatch, push)
    event = _saturday_event()

    cal_helpers._enforce_meeting_weekend_rule(event, _meeting_stub(), object())

    assert to_local_datetime(event.starts_at).date() == datetime.date(2026, 7, 20)
    assert len(push.pushed_events) == 1
    assert push.pushed_events[0] == (event.starts_at, event.ends_at)
    assert action_log.entries[0][:2] == (42, "google_meeting_weekend_shift")
    assert action_log.entries[0][3] == 7


def test_inbound_business_day_event_triggers_no_writeback(monkeypatch):
    push = FakeGooglePushRecorder()
    action_log = _patch_collaborators(monkeypatch, push)
    event = _inbound_event(
        datetime.datetime(2026, 7, 20, 9, 0),
        datetime.datetime(2026, 7, 20, 10, 0),
    )

    cal_helpers._enforce_meeting_weekend_rule(event, _meeting_stub(), object())

    assert push.pushed_events == []
    assert action_log.entries == []


def test_writeback_echo_does_not_retrigger_shift(monkeypatch):
    # Anti-loop: o evento corrigido (dia útil) que volta pelo webhook passa de
    # novo pela regra e ela precisa ser no-op — sem novo push nem novo log.
    push = FakeGooglePushRecorder()
    action_log = _patch_collaborators(monkeypatch, push)
    event = _saturday_event()
    meeting = _meeting_stub()

    cal_helpers._enforce_meeting_weekend_rule(event, meeting, object())
    cal_helpers._enforce_meeting_weekend_rule(event, meeting, object())

    assert len(push.pushed_events) == 1
    assert len(action_log.entries) == 1


def test_shift_without_connection_keeps_local_business_day(monkeypatch):
    push = FakeGooglePushRecorder()
    _patch_collaborators(monkeypatch, push)
    event = _saturday_event()

    cal_helpers._enforce_meeting_weekend_rule(event, _meeting_stub(), None)

    assert to_local_datetime(event.starts_at).date() == datetime.date(2026, 7, 20)
    assert push.pushed_events == []


def test_push_failure_marks_sync_error_and_keeps_shift(monkeypatch):
    _patch_collaborators(monkeypatch, FakeGooglePushFailure())
    event = _saturday_event()

    cal_helpers._enforce_meeting_weekend_rule(event, _meeting_stub(), object())

    assert to_local_datetime(event.starts_at).date() == datetime.date(2026, 7, 20)
    assert event.sync_status == "error"
    assert event.sync_error == "google indisponível"


def test_shifted_event_propagates_business_day_to_etapa():
    event = _saturday_event()
    shift_weekend_calendar_event(event)
    meeting = SimpleNamespace(
        calendar_event_id=1,
        google_event_id="gid-1",
        google_calendar_id="primary",
        starts_at=None,
        ends_at=None,
        is_all_day=False,
        timezone="America/Sao_Paulo",
        description=None,
        location=None,
        meet_link=None,
        sync_status="ok",
        sync_error=None,
        google_owner_email="dono@example.com",
    )
    etapa = SimpleNamespace(
        descricao="x",
        data_inicio=None,
        data_fim=None,
        responsavel=None,
        responsaveis=[],
        iniciada=True,
        done=True,
        entry_type="google_meeting",
    )

    update_meeting_from_calendar_event(meeting, event)
    sync_etapa_from_meeting(etapa, meeting, title=event.title)

    assert etapa.data_inicio == datetime.date(2026, 7, 20)
    assert etapa.data_inicio.weekday() < 5


def test_weekend_shift_logs_history_without_authenticated_user(
    app, seed_data, monkeypatch
):
    # Webhook do Google roda sem g.user: o log real precisa gravar mesmo assim.
    monkeypatch.setattr(
        cal_helpers, "_sync_local_event_to_google", FakeGooglePushRecorder()
    )
    event = _saturday_event()
    meeting = SimpleNamespace(
        project_id=seed_data["project_id"],
        creator_user_id=seed_data["user_id"],
        timezone="America/Sao_Paulo",
    )

    with app.test_request_context("/webhooks/google/calendar"):
        cal_helpers._enforce_meeting_weekend_rule(event, meeting, None)
        db.session.commit()

    with app.app_context():
        entry = ProjectHistory.query.filter_by(
            project_id=seed_data["project_id"],
            action_type="google_meeting_weekend_shift",
        ).first()
        assert entry is not None
        assert entry.user_id == seed_data["user_id"]


def test_weekend_shift_actor_prefers_connection_user_over_meeting_creator():
    connection = SimpleNamespace(user_id=99)

    assert cal_helpers._weekend_shift_actor_id(_meeting_stub(), connection) == 99
    assert cal_helpers._weekend_shift_actor_id(_meeting_stub(), None) == 7
