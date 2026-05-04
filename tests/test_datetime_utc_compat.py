import datetime

from services.calendar_core import to_local_datetime, to_utc_naive
from time_utils import utc_now


def test_login_renders_when_datetime_utc_alias_is_unavailable(client, monkeypatch):
    monkeypatch.delattr(datetime, "UTC", raising=False)

    response = client.get("/login")

    assert response.status_code == 200
    assert "Projetos" in response.get_data(as_text=True)


def test_utc_helpers_work_when_datetime_utc_alias_is_unavailable(monkeypatch):
    monkeypatch.delattr(datetime, "UTC", raising=False)

    now = utc_now()
    local = to_local_datetime(datetime.datetime(2026, 1, 15, 12, 0))
    utc_naive = to_utc_naive(local)

    assert now.tzinfo is None
    assert utc_naive == datetime.datetime(2026, 1, 15, 12, 0)
