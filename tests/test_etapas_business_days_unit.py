import datetime

import routes.etapas.helpers as etapa_helpers


def test_add_business_days_skips_full_weeks_without_day_by_day_scan(monkeypatch):
    calls = []
    original_is_business_day = etapa_helpers._is_business_day

    def spy_is_business_day(date_value):
        calls.append(date_value)
        return original_is_business_day(date_value)

    monkeypatch.setattr(etapa_helpers, "_is_business_day", spy_is_business_day)

    result = etapa_helpers._add_business_days(datetime.date(2026, 1, 5), 1_000_000)

    assert result == datetime.date(5859, 1, 31)
    assert len(calls) == 0


def test_add_business_days_preserves_weekend_start_behavior():
    result = etapa_helpers._add_business_days(datetime.date(2026, 1, 24), 5)

    assert result == datetime.date(2026, 1, 30)


def test_add_business_days_preserves_small_backward_shift_behavior():
    result = etapa_helpers._add_business_days(datetime.date(2026, 1, 12), -3)

    assert result == datetime.date(2026, 1, 7)
