"""Unidade de services.password_policy.validate_password_strength (achado 5.1.3)."""

import pytest

from services.password_policy import validate_password_strength


@pytest.mark.parametrize(
    "password",
    ["senhaForte12", "12345678", "        x", "x" * 128, "áéíóúçãâê"],
)
def test_accepts_valid_passwords(password):
    assert validate_password_strength(password) is None


@pytest.mark.parametrize(
    "password",
    [None, "", "   ", "curta", "1234567", " " * 8, "x" * 129],
)
def test_rejects_weak_or_empty_passwords(password):
    assert validate_password_strength(password) is not None
