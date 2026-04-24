"""Testes unitários de services.calendar_sync.

Cobre:
  * ensure_google_access_token — caminho de cache vs refresh, rotação de
    refresh_token, tratamento de expires_in inválido/None.
  * sync_local_event_to_google — update OK, update 404 caindo em create, e
    create puro quando ainda não há google_event_id.
Mocka as chamadas externas (refresh/create/update) para não tocar rede."""

import datetime
from types import SimpleNamespace

import pytest

from services import calendar_sync
from services.calendar_sync import (
    ensure_google_access_token,
    sync_local_event_to_google,
)
from services.google_calendar import GoogleCalendarError


def _connection(**overrides):
    base = dict(
        access_token="old-token",
        refresh_token="refresh-xyz",
        token_expires_at=None,
        calendar_id="primary",
        google_account_id="acc-1",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _local_event(**overrides):
    now = datetime.datetime(2026, 1, 15, 13, 0)
    base = dict(
        title="Reunião",
        description="desc",
        location="loc",
        starts_at=now,
        ends_at=now + datetime.timedelta(hours=1),
        google_event_id=None,
        google_calendar_id=None,
        source="app",
        sync_status="pending",
        sync_error=None,
        last_synced_at=None,
        meet_link=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# ensure_google_access_token
# ---------------------------------------------------------------------------


def test_ensure_access_token_returns_cached_when_not_expired(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    called = []
    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: called.append(True) or {"access_token": "new"},
    )

    connection = _connection(
        access_token="cached-token",
        token_expires_at=now + datetime.timedelta(minutes=10),
    )

    token = ensure_google_access_token({}, connection)

    assert token == "cached-token"
    assert connection.access_token == "cached-token"
    assert called == []


def test_ensure_access_token_refreshes_when_within_60s_margin(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: {"access_token": "new-token", "expires_in": 3600},
    )

    connection = _connection(
        access_token="cached-token",
        token_expires_at=now + datetime.timedelta(seconds=30),
    )

    token = ensure_google_access_token({}, connection)

    assert token == "new-token"
    assert connection.access_token == "new-token"
    assert connection.token_expires_at == now + datetime.timedelta(seconds=3600)


def test_ensure_access_token_refresh_when_no_access_token(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: {"access_token": "brand-new"},
    )

    connection = _connection(access_token=None, token_expires_at=None)
    token = ensure_google_access_token({}, connection)

    assert token == "brand-new"
    assert connection.access_token == "brand-new"


def test_ensure_access_token_force_refresh_ignores_cache(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: {"access_token": "forced", "expires_in": 100},
    )

    connection = _connection(
        access_token="still-valid",
        token_expires_at=now + datetime.timedelta(hours=2),
    )

    token = ensure_google_access_token({}, connection, force_refresh=True)

    assert token == "forced"
    assert connection.token_expires_at == now + datetime.timedelta(seconds=100)


def test_ensure_access_token_rotates_refresh_token_when_present(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: {
            "access_token": "new",
            "expires_in": 120,
            "refresh_token": "rotated-refresh",
        },
    )

    connection = _connection(refresh_token="old-refresh")
    ensure_google_access_token({}, connection)

    assert connection.refresh_token == "rotated-refresh"


def test_ensure_access_token_keeps_refresh_token_when_absent(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: {"access_token": "new", "expires_in": 60},
    )

    connection = _connection(refresh_token="keep-me")
    ensure_google_access_token({}, connection)

    assert connection.refresh_token == "keep-me"


@pytest.mark.parametrize("bogus", [None, "abc", object()])
def test_ensure_access_token_coerces_invalid_expires_in(monkeypatch, bogus):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: {"access_token": "new", "expires_in": bogus},
    )

    connection = _connection()
    ensure_google_access_token({}, connection)

    if bogus is None:
        # expires_in ausente: não recalcula o vencimento.
        assert connection.token_expires_at is None
    else:
        # Valor não-numérico → cai em 0s (expira imediatamente).
        assert connection.token_expires_at == now


def test_ensure_access_token_handles_negative_expires_in(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)

    monkeypatch.setattr(
        calendar_sync,
        "refresh_google_access_token",
        lambda *a, **kw: {"access_token": "new", "expires_in": -10},
    )

    connection = _connection()
    ensure_google_access_token({}, connection)

    # Clampeia em 0, sem voltar no tempo.
    assert connection.token_expires_at == now


# ---------------------------------------------------------------------------
# sync_local_event_to_google
# ---------------------------------------------------------------------------


def _patch_token(monkeypatch, token="access-abc"):
    monkeypatch.setattr(
        calendar_sync,
        "ensure_google_access_token",
        lambda config, connection, **kw: token,
    )


def test_sync_without_connection_sets_pending_status():
    event = _local_event()
    out = sync_local_event_to_google({}, event, None)

    assert out is None
    assert event.sync_status == "pending"
    assert "não configurada" in event.sync_error


def test_sync_creates_when_no_google_event_id(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)
    _patch_token(monkeypatch)

    captured = {}

    def _fake_create(
        config, *, access_token, calendar_id, event_payload, conference_data_version
    ):
        captured["calendar_id"] = calendar_id
        captured["payload"] = event_payload
        captured["conf"] = conference_data_version
        return {
            "id": "remote-abc",
            "hangoutLink": "https://meet.google.com/x",
        }

    monkeypatch.setattr(calendar_sync, "create_google_calendar_event", _fake_create)

    event = _local_event()
    connection = _connection()
    remote = sync_local_event_to_google({}, event, connection, create_conference=True)

    assert remote["id"] == "remote-abc"
    assert event.google_event_id == "remote-abc"
    assert event.google_calendar_id == "primary"
    assert event.sync_status == "ok"
    assert event.sync_error is None
    assert event.last_synced_at == now
    assert event.meet_link == "https://meet.google.com/x"
    assert captured["conf"] == 1


def test_sync_without_conference_sets_version_zero(monkeypatch):
    monkeypatch.setattr(
        calendar_sync, "utc_now", lambda: datetime.datetime(2026, 1, 15)
    )
    _patch_token(monkeypatch)

    captured = {}

    def _fake_create(
        config, *, access_token, calendar_id, event_payload, conference_data_version
    ):
        captured["conf"] = conference_data_version
        return {"id": "r1"}

    monkeypatch.setattr(calendar_sync, "create_google_calendar_event", _fake_create)

    sync_local_event_to_google(
        {}, _local_event(), _connection(), create_conference=False
    )
    assert captured["conf"] == 0


def test_sync_update_success_updates_local_fields(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)
    _patch_token(monkeypatch)

    monkeypatch.setattr(
        calendar_sync,
        "update_google_calendar_event",
        lambda *a, **kw: {"id": "remote-existing"},
    )

    def _should_not_create(*a, **kw):  # pragma: no cover - nunca deve ser chamado
        raise AssertionError("create não deveria ser chamado")

    monkeypatch.setattr(
        calendar_sync, "create_google_calendar_event", _should_not_create
    )

    event = _local_event(google_event_id="remote-existing")
    sync_local_event_to_google({}, event, _connection())

    assert event.sync_status == "ok"
    assert event.google_event_id == "remote-existing"


def test_sync_update_404_falls_back_to_create(monkeypatch):
    now = datetime.datetime(2026, 1, 15, 12, 0)
    monkeypatch.setattr(calendar_sync, "utc_now", lambda: now)
    _patch_token(monkeypatch)

    def _fake_update(*args, **kwargs):
        raise GoogleCalendarError("gone", status_code=404)

    monkeypatch.setattr(calendar_sync, "update_google_calendar_event", _fake_update)
    monkeypatch.setattr(
        calendar_sync,
        "create_google_calendar_event",
        lambda *a, **kw: {"id": "new-remote"},
    )

    event = _local_event(google_event_id="stale-id")
    sync_local_event_to_google({}, event, _connection())

    assert event.google_event_id == "new-remote"
    assert event.sync_status == "ok"


def test_sync_update_500_propagates(monkeypatch):
    monkeypatch.setattr(
        calendar_sync, "utc_now", lambda: datetime.datetime(2026, 1, 15)
    )
    _patch_token(monkeypatch)

    def _fake_update(*args, **kwargs):
        raise GoogleCalendarError("boom", status_code=500)

    monkeypatch.setattr(calendar_sync, "update_google_calendar_event", _fake_update)

    event = _local_event(google_event_id="id-xyz")
    with pytest.raises(GoogleCalendarError):
        sync_local_event_to_google({}, event, _connection())


def test_sync_uses_connection_calendar_id_when_present(monkeypatch):
    monkeypatch.setattr(
        calendar_sync, "utc_now", lambda: datetime.datetime(2026, 1, 15)
    )
    _patch_token(monkeypatch)

    captured = {}

    def _fake_create(config, *, access_token, calendar_id, **kwargs):
        captured["calendar_id"] = calendar_id
        return {"id": "x"}

    monkeypatch.setattr(calendar_sync, "create_google_calendar_event", _fake_create)

    connection = _connection(calendar_id="other-cal@group.calendar.google.com")
    sync_local_event_to_google({}, _local_event(), connection)

    assert captured["calendar_id"] == "other-cal@group.calendar.google.com"


# ---------------------------------------------------------------------------
# delete_remote_event
# ---------------------------------------------------------------------------


def test_delete_remote_event_returns_false_when_no_connection():
    assert calendar_sync.delete_remote_event({}, None, google_event_id="x") is False


def test_delete_remote_event_returns_false_when_no_event_id():
    connection = _connection()
    assert (
        calendar_sync.delete_remote_event({}, connection, google_event_id="") is False
    )


def test_delete_remote_event_calls_api(monkeypatch):
    _patch_token(monkeypatch)
    captured = {}

    def _fake_delete(config, *, access_token, calendar_id, event_id):
        captured["calendar_id"] = calendar_id
        captured["event_id"] = event_id
        return True

    monkeypatch.setattr(calendar_sync, "delete_google_calendar_event", _fake_delete)

    out = calendar_sync.delete_remote_event(
        {},
        _connection(),
        google_event_id="evt-1",
        google_calendar_id="cal-x",
    )
    assert out is True
    assert captured == {"calendar_id": "cal-x", "event_id": "evt-1"}
