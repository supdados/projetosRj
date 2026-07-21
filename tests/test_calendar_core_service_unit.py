"""Testes unitários de services.calendar_core.

Cobre funções puras: parse_form_datetime, to_utc_naive/to_local_datetime,
parse_google_event_datetime, google_event_payload, extract_meet_link.
Não usa banco nem rede."""

import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from services import calendar_core
from services.calendar_core import (
    TIMEZONE_BR,
    extract_meet_link,
    format_human_datetime,
    format_input_datetime,
    google_event_payload,
    parse_form_datetime,
    parse_google_event_datetime,
    to_local_datetime,
    to_utc_naive,
    utc_naive_to_rfc3339,
)

# ---------------------------------------------------------------------------
# to_utc_naive / to_local_datetime / formatters
# ---------------------------------------------------------------------------


def test_to_utc_naive_assumes_brasilia_when_naive():
    local = datetime.datetime(2026, 1, 15, 10, 30)
    utc = to_utc_naive(local)
    # Brasília é UTC-3 → 10:30 BRT == 13:30 UTC.
    assert utc == datetime.datetime(2026, 1, 15, 13, 30)
    assert utc.tzinfo is None


def test_to_utc_naive_respects_aware_tz():
    aware = datetime.datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    utc = to_utc_naive(aware)
    assert utc.tzinfo is None
    # Lisboa no inverno é UTC+0, então 12:00 Lisboa == 12:00 UTC.
    assert utc == datetime.datetime(2026, 1, 15, 12, 0)


def test_to_local_datetime_returns_none_when_none():
    assert to_local_datetime(None) is None


def test_to_local_datetime_converts_utc_to_brasilia():
    utc_naive = datetime.datetime(2026, 1, 15, 13, 30)
    local = to_local_datetime(utc_naive)
    assert local.tzinfo is not None
    assert local.hour == 10
    assert local.minute == 30


def test_format_input_datetime_returns_empty_when_none():
    assert format_input_datetime(None) == ""


def test_format_input_datetime_renders_local_slot():
    utc_naive = datetime.datetime(2026, 1, 15, 13, 30)
    assert format_input_datetime(utc_naive) == "2026-01-15T10:30"


def test_format_human_datetime_placeholder_when_none():
    assert format_human_datetime(None) == "-"


def test_format_human_datetime_renders_br_format():
    utc_naive = datetime.datetime(2026, 1, 15, 13, 30)
    assert format_human_datetime(utc_naive) == "15/01/2026 10:30"


def test_utc_naive_to_rfc3339_uses_z_suffix():
    utc_naive = datetime.datetime(2026, 1, 15, 13, 30, 45)
    assert utc_naive_to_rfc3339(utc_naive) == "2026-01-15T13:30:45Z"


# ---------------------------------------------------------------------------
# parse_form_datetime
# ---------------------------------------------------------------------------


def test_parse_form_datetime_empty_returns_none():
    assert parse_form_datetime(None) is None
    assert parse_form_datetime("") is None
    assert parse_form_datetime("   ") is None


def test_parse_form_datetime_converts_local_to_utc():
    utc = parse_form_datetime("2026-01-15T10:30")
    assert utc == datetime.datetime(2026, 1, 15, 13, 30)


@pytest.mark.parametrize("value", ["not-a-date", "15/01/2026 10:30", "2026-01-15"])
def test_parse_form_datetime_invalid_raises_value_error(value):
    with pytest.raises(ValueError, match="Formato de data/hora"):
        parse_form_datetime(value)


# ---------------------------------------------------------------------------
# extract_meet_link
# ---------------------------------------------------------------------------


def test_extract_meet_link_prefers_video_entry_point():
    remote = {
        "conferenceData": {
            "entryPoints": [
                {"entryPointType": "more", "uri": "https://more"},
                {"entryPointType": "video", "uri": "https://meet.google.com/xxx"},
            ],
        },
        "hangoutLink": "https://hangout.legacy",
    }
    assert extract_meet_link(remote) == "https://meet.google.com/xxx"


def test_extract_meet_link_falls_back_to_hangout_link():
    remote = {"conferenceData": {"entryPoints": []}, "hangoutLink": "https://hangout"}
    assert extract_meet_link(remote) == "https://hangout"


def test_extract_meet_link_returns_none_when_no_link():
    assert extract_meet_link({}) is None


# ---------------------------------------------------------------------------
# google_event_payload
# ---------------------------------------------------------------------------


def _event_stub():
    return SimpleNamespace(
        title="Reunião",
        description="Descrição",
        location="Sala A",
        starts_at=datetime.datetime(2026, 1, 15, 13, 0),
        ends_at=datetime.datetime(2026, 1, 15, 14, 0),
        is_all_day=False,
    )


def _all_day_event_stub(*, days=1):
    # Meia-noite BRT == 03:00 UTC; fim inclusivo local == 23:59 do último dia.
    return SimpleNamespace(
        title="Feriado",
        description=None,
        location=None,
        starts_at=datetime.datetime(2026, 1, 15, 3, 0),
        ends_at=datetime.datetime(2026, 1, 15 + days, 2, 59),
        is_all_day=True,
    )


def test_google_event_payload_without_conference():
    payload = google_event_payload(_event_stub(), create_conference=False)

    assert payload["summary"] == "Reunião"
    assert payload["description"] == "Descrição"
    assert payload["location"] == "Sala A"
    assert payload["start"]["dateTime"] == "2026-01-15T13:00:00Z"
    assert payload["start"]["timeZone"] == "UTC"
    assert payload["end"]["dateTime"] == "2026-01-15T14:00:00Z"
    assert "conferenceData" not in payload


def test_google_event_payload_with_conference_adds_create_request():
    payload = google_event_payload(_event_stub(), create_conference=True)

    assert "conferenceData" in payload
    create_request = payload["conferenceData"]["createRequest"]
    assert "requestId" in create_request
    assert create_request["conferenceSolutionKey"] == {"type": "hangoutsMeet"}


def test_google_event_payload_all_day_uses_date_keys():
    payload = google_event_payload(_all_day_event_stub())

    assert payload["start"] == {"date": "2026-01-15"}
    # Fim exclusivo: dia seguinte ao último dia do evento.
    assert payload["end"] == {"date": "2026-01-16"}
    assert "dateTime" not in payload["start"]
    assert "dateTime" not in payload["end"]


def test_google_event_payload_all_day_multi_day_end_exclusive():
    payload = google_event_payload(_all_day_event_stub(days=3))

    assert payload["start"] == {"date": "2026-01-15"}
    assert payload["end"] == {"date": "2026-01-18"}


def test_google_event_payload_without_is_all_day_attr_defaults_to_timed():
    event = _event_stub()
    del event.is_all_day
    payload = google_event_payload(event)
    assert "dateTime" in payload["start"]


def test_all_day_round_trip_preserves_flag_and_local_dates():
    event = _all_day_event_stub(days=2)
    payload = google_event_payload(event)

    starts_at, starts_all_day = parse_google_event_datetime(payload["start"])
    ends_at, ends_all_day = parse_google_event_datetime(payload["end"])

    assert starts_all_day is True
    assert ends_all_day is True
    assert starts_at == event.starts_at
    # Parse devolve o fim exclusivo; a convenção local (helpers) subtrai 1 min.
    assert ends_at - datetime.timedelta(minutes=1) == event.ends_at


def test_google_event_payload_handles_empty_description_and_location():
    event = _event_stub()
    event.description = None
    event.location = None
    payload = google_event_payload(event)
    assert payload["description"] == ""
    assert payload["location"] == ""


# ---------------------------------------------------------------------------
# parse_google_event_datetime
# ---------------------------------------------------------------------------


def test_parse_google_event_datetime_with_z_suffix():
    dt, is_all_day = parse_google_event_datetime({"dateTime": "2026-01-15T13:30:00Z"})
    assert dt == datetime.datetime(2026, 1, 15, 13, 30)
    assert is_all_day is False


def test_parse_google_event_datetime_with_named_timezone():
    dt, is_all_day = parse_google_event_datetime(
        {"dateTime": "2026-01-15T10:30:00", "timeZone": "America/Sao_Paulo"}
    )
    assert dt == datetime.datetime(2026, 1, 15, 13, 30)
    assert is_all_day is False


def test_parse_google_event_datetime_with_offset_in_datetime():
    dt, is_all_day = parse_google_event_datetime(
        {"dateTime": "2026-01-15T10:30:00-03:00", "timeZone": "America/Sao_Paulo"}
    )
    assert dt == datetime.datetime(2026, 1, 15, 13, 30)
    assert is_all_day is False


def test_parse_google_event_datetime_all_day_returns_local_midnight_in_utc():
    dt, is_all_day = parse_google_event_datetime(
        {"date": "2026-01-15", "timeZone": "America/Sao_Paulo"}
    )
    # Meia-noite BRT == 03:00 UTC.
    assert dt == datetime.datetime(2026, 1, 15, 3, 0)
    assert is_all_day is True


def test_parse_google_event_datetime_all_day_defaults_to_local_tz_when_missing():
    dt, is_all_day = parse_google_event_datetime({"date": "2026-01-15"})
    assert dt == datetime.datetime(2026, 1, 15, 3, 0)
    assert is_all_day is True


def test_parse_google_event_datetime_all_day_fallback_when_tz_invalid():
    dt, is_all_day = parse_google_event_datetime(
        {"date": "2026-01-15", "timeZone": "Inventado/Zona"}
    )
    # Zona inválida cai no TIMEZONE_BR (UTC-3) → 03:00 UTC.
    assert dt == datetime.datetime(2026, 1, 15, 3, 0)
    assert is_all_day is True


def test_parse_google_event_datetime_empty_returns_none_none():
    assert parse_google_event_datetime({}) == (None, None)
    assert parse_google_event_datetime(None) == (None, None)


def test_parse_google_event_datetime_naive_dt_with_invalid_tz_falls_back_to_utc():
    dt, is_all_day = parse_google_event_datetime(
        {"dateTime": "2026-01-15T13:30:00", "timeZone": "Bad/Zone"}
    )
    assert dt == datetime.datetime(2026, 1, 15, 13, 30)
    assert is_all_day is False
