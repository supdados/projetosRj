"""Testes unitários de services.project_meetings.

Cobre helpers puros sem depender de banco:
  * is_google_meeting_stage
  * can_manage_project_meeting
  * local_meeting_dates
  * meeting_time_summary / meeting_time_display
  * sync_etapa_from_meeting
  * update_meeting_from_calendar_event / mark_project_meeting_sync_error
"""

import datetime
from types import SimpleNamespace

from services.project_meetings import (
    MEETING_ENTRY_TYPE,
    can_manage_project_meeting,
    is_google_meeting_stage,
    local_meeting_dates,
    mark_project_meeting_sync_error,
    meeting_time_display,
    meeting_time_summary,
    sync_etapa_from_meeting,
    update_meeting_from_calendar_event,
)


def _meeting(**overrides):
    base = dict(
        starts_at=datetime.datetime(2026, 1, 15, 13, 0),
        ends_at=datetime.datetime(2026, 1, 15, 14, 0),
        is_all_day=False,
        google_owner_account_id="owner-a",
        google_owner_email="dono@example.com",
        etapa=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# is_google_meeting_stage
# ---------------------------------------------------------------------------


def test_is_google_meeting_stage_true_for_google_meeting_entry_type():
    etapa = SimpleNamespace(entry_type="google_meeting")
    assert is_google_meeting_stage(etapa) is True


def test_is_google_meeting_stage_false_for_manual_entry_type():
    etapa = SimpleNamespace(entry_type="manual")
    assert is_google_meeting_stage(etapa) is False


def test_is_google_meeting_stage_false_for_none():
    assert is_google_meeting_stage(None) is False


# ---------------------------------------------------------------------------
# can_manage_project_meeting
# ---------------------------------------------------------------------------


def test_can_manage_returns_true_when_account_id_matches():
    connection = SimpleNamespace(google_account_id="acc-1")
    meeting = _meeting(google_owner_account_id="acc-1")
    assert can_manage_project_meeting(connection, meeting) is True


def test_can_manage_returns_false_when_account_id_differs():
    connection = SimpleNamespace(google_account_id="acc-1")
    meeting = _meeting(google_owner_account_id="acc-2")
    assert can_manage_project_meeting(connection, meeting) is False


def test_can_manage_returns_false_when_account_id_is_empty():
    connection = SimpleNamespace(google_account_id="")
    meeting = _meeting(google_owner_account_id="")
    assert can_manage_project_meeting(connection, meeting) is False


def test_can_manage_returns_false_when_connection_missing():
    meeting = _meeting()
    assert can_manage_project_meeting(None, meeting) is False


def test_can_manage_returns_false_when_meeting_missing():
    connection = SimpleNamespace(google_account_id="acc-1")
    assert can_manage_project_meeting(connection, None) is False


def test_can_manage_strips_whitespace_from_account_ids():
    connection = SimpleNamespace(google_account_id="  acc-1  ")
    meeting = _meeting(google_owner_account_id="acc-1")
    assert can_manage_project_meeting(connection, meeting) is True


# ---------------------------------------------------------------------------
# local_meeting_dates
# ---------------------------------------------------------------------------


def test_local_meeting_dates_converts_to_brasilia():
    meeting = _meeting(
        starts_at=datetime.datetime(2026, 1, 15, 13, 0),
        ends_at=datetime.datetime(2026, 1, 15, 14, 30),
    )
    start_local, end_local = local_meeting_dates(meeting)
    assert start_local.hour == 10 and start_local.minute == 0
    assert end_local.hour == 11 and end_local.minute == 30


def test_local_meeting_dates_returns_none_for_none_meeting():
    assert local_meeting_dates(None) == (None, None)


# ---------------------------------------------------------------------------
# meeting_time_summary
# ---------------------------------------------------------------------------


def test_meeting_time_summary_same_day_uses_time_range():
    meeting = _meeting(
        starts_at=datetime.datetime(2026, 1, 15, 13, 0),
        ends_at=datetime.datetime(2026, 1, 15, 14, 30),
    )
    # Converte para BRT (UTC-3): 10:00 - 11:30.
    assert meeting_time_summary(meeting) == "10:00 - 11:30"


def test_meeting_time_summary_all_day_returns_dia_inteiro():
    meeting = _meeting(is_all_day=True)
    assert meeting_time_summary(meeting) == "Dia inteiro"


def test_meeting_time_summary_different_dates_uses_full_datetime():
    meeting = _meeting(
        starts_at=datetime.datetime(2026, 1, 15, 13, 0),
        ends_at=datetime.datetime(2026, 1, 16, 14, 0),
    )
    summary = meeting_time_summary(meeting)
    assert "15/01/2026 10:00" in summary
    assert "16/01/2026 11:00" in summary


def test_meeting_time_summary_without_bounds_returns_placeholder():
    meeting = _meeting(starts_at=None, ends_at=None)
    assert meeting_time_summary(meeting) == "Sem horário"


# ---------------------------------------------------------------------------
# meeting_time_display
# ---------------------------------------------------------------------------


def test_meeting_time_display_start():
    meeting = _meeting(starts_at=datetime.datetime(2026, 1, 15, 13, 0))
    assert meeting_time_display(meeting, boundary="start") == "10:00"


def test_meeting_time_display_end():
    meeting = _meeting(ends_at=datetime.datetime(2026, 1, 15, 14, 30))
    assert meeting_time_display(meeting, boundary="end") == "11:30"


def test_meeting_time_display_all_day():
    meeting = _meeting(is_all_day=True)
    assert meeting_time_display(meeting) == "Dia inteiro"


def test_meeting_time_display_empty_returns_empty_string():
    meeting = _meeting(starts_at=None)
    assert meeting_time_display(meeting, boundary="start") == ""


# ---------------------------------------------------------------------------
# sync_etapa_from_meeting
# ---------------------------------------------------------------------------


def test_sync_etapa_from_meeting_copies_dates_title_and_responsavel():
    etapa = SimpleNamespace(
        descricao="Antigo",
        data_inicio=None,
        data_fim=None,
        responsavel="original",
        iniciada=True,
        done=True,
        entry_type="manual",
    )
    meeting = _meeting(
        starts_at=datetime.datetime(2026, 1, 15, 13, 0),
        ends_at=datetime.datetime(2026, 1, 16, 14, 0),
        google_owner_email="dono@example.com",
    )

    sync_etapa_from_meeting(etapa, meeting, title="Reunião X")

    assert etapa.descricao == "Reunião X"
    assert etapa.data_inicio == datetime.date(2026, 1, 15)
    assert etapa.data_fim == datetime.date(2026, 1, 16)
    assert etapa.responsavel == "dono@example.com"
    assert etapa.iniciada is False
    assert etapa.done is False
    assert etapa.entry_type == MEETING_ENTRY_TYPE


def test_sync_etapa_from_meeting_preserves_responsavel_when_email_empty():
    etapa = SimpleNamespace(
        descricao="x",
        data_inicio=None,
        data_fim=None,
        responsavel="keep",
        iniciada=False,
        done=False,
        entry_type="manual",
    )
    meeting = _meeting(google_owner_email=None)
    sync_etapa_from_meeting(etapa, meeting)
    assert etapa.responsavel == "keep"


def test_sync_etapa_from_meeting_handles_missing_inputs():
    # Nenhum dos lados: retorna o primeiro argumento sem estourar.
    assert sync_etapa_from_meeting(None, _meeting()) is None
    etapa = SimpleNamespace(
        descricao="x",
        data_inicio=None,
        data_fim=None,
        responsavel="r",
        iniciada=False,
        done=False,
        entry_type="manual",
    )
    assert sync_etapa_from_meeting(etapa, None) is etapa


def test_sync_etapa_from_meeting_preserves_existing_title_when_none():
    etapa = SimpleNamespace(
        descricao="Antigo",
        data_inicio=None,
        data_fim=None,
        responsavel="r",
        iniciada=False,
        done=False,
        entry_type="manual",
    )
    sync_etapa_from_meeting(etapa, _meeting(), title=None)
    assert etapa.descricao == "Antigo"


# ---------------------------------------------------------------------------
# update_meeting_from_calendar_event / mark_project_meeting_sync_error
# ---------------------------------------------------------------------------


def test_update_meeting_from_calendar_event_copies_fields():
    meeting = SimpleNamespace(timezone="America/Sao_Paulo")
    event = SimpleNamespace(
        id=101,
        google_event_id="g-1",
        google_calendar_id="cal-1",
        starts_at=datetime.datetime(2026, 2, 1, 12, 0),
        ends_at=datetime.datetime(2026, 2, 1, 13, 0),
        is_all_day=True,
        timezone="America/New_York",
        description="desc",
        location="loc",
        meet_link="https://meet",
        sync_status="ok",
        sync_error=None,
    )
    out = update_meeting_from_calendar_event(meeting, event)

    assert out is meeting
    assert meeting.calendar_event_id == 101
    assert meeting.google_event_id == "g-1"
    assert meeting.google_calendar_id == "cal-1"
    assert meeting.starts_at == datetime.datetime(2026, 2, 1, 12, 0)
    assert meeting.timezone == "America/New_York"
    assert meeting.is_all_day is True
    assert meeting.meet_link == "https://meet"


def test_update_meeting_from_calendar_event_handles_missing():
    assert update_meeting_from_calendar_event(None, SimpleNamespace()) is None
    ghost = SimpleNamespace()
    assert update_meeting_from_calendar_event(ghost, None) is ghost


def test_mark_project_meeting_sync_error_sets_status_and_resets_etapa():
    etapa = SimpleNamespace(iniciada=True, done=True)
    meeting = SimpleNamespace(sync_status="ok", sync_error=None, etapa=etapa)

    mark_project_meeting_sync_error(meeting, message="falhou")

    assert meeting.sync_status == "error"
    assert meeting.sync_error == "falhou"
    assert etapa.iniciada is False
    assert etapa.done is False


def test_mark_project_meeting_sync_error_is_noop_when_meeting_missing():
    # Não deve levantar.
    mark_project_meeting_sync_error(None, message="x")
