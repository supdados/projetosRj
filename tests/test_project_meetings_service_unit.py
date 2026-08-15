"""Testes unitários de services.project_meetings.

Cobre helpers puros sem depender de banco:
  * is_google_meeting_stage
  * can_manage_project_meeting
  * local_meeting_dates
  * meeting_time_summary / meeting_time_display
  * sync_etapa_from_meeting
  * update_meeting_from_calendar_event / mark_project_meeting_sync_error
  * _shift_weekend_meeting_payload / _weekend_shift_message
"""

import datetime
from types import SimpleNamespace

from services.calendar_core import to_local_datetime, to_utc_naive
from services.project_meetings import (
    MEETING_ENTRY_TYPE,
    _shift_weekend_meeting_payload,
    _weekend_shift_message,
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
        responsaveis=[],
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
    # Escrita via N:N (único escritor); o espelho vira derivado.
    assert [(r.area_id, r.label) for r in etapa.responsaveis] == [
        (None, "dono@example.com")
    ]
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
        responsaveis=[],
        iniciada=False,
        done=False,
        entry_type="manual",
    )
    meeting = _meeting(google_owner_email=None)
    sync_etapa_from_meeting(etapa, meeting)
    assert etapa.responsavel == "keep"
    assert etapa.responsaveis == []


def test_sync_etapa_from_meeting_replaces_previous_nn_rows_with_owner_email():
    from models import EtapaResponsavel

    etapa = SimpleNamespace(
        descricao="x",
        data_inicio=None,
        data_fim=None,
        responsavel="SUBEXE",
        responsaveis=[EtapaResponsavel(area_id=None, label="SUBEXE")],
        iniciada=False,
        done=False,
        entry_type="manual",
    )
    sync_etapa_from_meeting(etapa, _meeting(google_owner_email="dono@example.com"))
    assert [(r.area_id, r.label) for r in etapa.responsaveis] == [
        (None, "dono@example.com")
    ]
    assert etapa.responsavel == "dono@example.com"


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
        responsaveis=[],
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


def _payload_for_local(start_local, end_local):
    return {
        "starts_at": to_utc_naive(start_local),
        "ends_at": to_utc_naive(end_local),
    }


def test_shift_weekend_meeting_payload_pushes_saturday_to_monday():
    # Regressão: reunião marcada num sábado (via /calendarios) precisa cair no
    # próximo dia útil, igual à edição manual de data_inicio de uma etapa.
    payload = _payload_for_local(
        datetime.datetime(2026, 7, 18, 14, 0),  # sábado
        datetime.datetime(2026, 7, 18, 15, 0),
    )

    shifted, shift = _shift_weekend_meeting_payload(payload)

    assert shift == (datetime.date(2026, 7, 18), datetime.date(2026, 7, 20))
    shifted_start = to_local_datetime(shifted["starts_at"])
    shifted_end = to_local_datetime(shifted["ends_at"])
    assert shifted_start.date() == datetime.date(2026, 7, 20)  # segunda
    assert shifted_start.hour == 14  # horário preservado
    assert (shifted_end - shifted_start) == datetime.timedelta(
        hours=1
    )  # duração preservada


def test_shift_weekend_meeting_payload_pushes_sunday_to_monday():
    payload = _payload_for_local(
        datetime.datetime(2026, 7, 19, 9, 0),  # domingo
        datetime.datetime(2026, 7, 19, 10, 0),
    )

    shifted, shift = _shift_weekend_meeting_payload(payload)

    assert shift == (datetime.date(2026, 7, 19), datetime.date(2026, 7, 20))
    assert to_local_datetime(shifted["starts_at"]).date() == datetime.date(2026, 7, 20)


def test_shift_weekend_meeting_payload_leaves_business_day_untouched():
    payload = _payload_for_local(
        datetime.datetime(2026, 7, 20, 9, 0),  # segunda
        datetime.datetime(2026, 7, 20, 10, 0),
    )

    shifted, shift = _shift_weekend_meeting_payload(payload)

    assert shift is None
    assert shifted == payload


def test_weekend_shift_message_formats_dates_br_and_handles_none():
    message = _weekend_shift_message(
        (datetime.date(2026, 7, 18), datetime.date(2026, 7, 20))
    )
    assert "18/07/2026" in message
    assert "20/07/2026" in message
    assert _weekend_shift_message(None) is None
