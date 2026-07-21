import datetime

import pytest

from time_utils import format_relative_time_pt

_NOW = datetime.datetime(2026, 7, 17, 12, 0, 0)


def _relative_for_days(days: int) -> str:
    return format_relative_time_pt(_NOW - datetime.timedelta(days=days), now=_NOW)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (1, "há 1 dia"),
        (6, "há 6 dias"),
        (7, "há 1 semana"),
        (13, "há 1 semana"),
        (14, "há 2 semanas"),
        (27, "há 3 semanas"),
        (28, "há 1 mês"),
        (29, "há 1 mês"),
        (30, "há 1 mês"),
        (59, "há 1 mês"),
        (60, "há 2 meses"),
        (359, "há 11 meses"),
        (360, "há 1 ano"),
        (364, "há 1 ano"),
        (365, "há 1 ano"),
        (729, "há 1 ano"),
        (730, "há 2 anos"),
    ],
)
def test_relative_time_day_boundaries(days: int, expected: str) -> None:
    assert _relative_for_days(days) == expected


@pytest.mark.parametrize("days", range(1, 800))
def test_relative_time_never_emits_zero_unit(days: int) -> None:
    assert "há 0 " not in _relative_for_days(days)
