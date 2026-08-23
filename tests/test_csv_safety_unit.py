"""Unidade de services.csv_safety.safe_csv_text (neutraliza CSV injection)."""

import pytest

from services.csv_safety import safe_csv_text


def test_none_vira_string_vazia():
    assert safe_csv_text(None) == ""


@pytest.mark.parametrize(
    "value,expected",
    [
        ("projeto normal", "projeto normal"),
        (42, "42"),
        ("  texto com espaço  ", "  texto com espaço  "),
    ],
)
def test_texto_sem_formula_passa_intacto(value, expected):
    assert safe_csv_text(value) == expected


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_prefixa_apostrofo_em_texto_com_formula(prefix):
    value = f'{prefix}HYPERLINK("http://evil")'
    assert safe_csv_text(value) == f"'{value}"


def test_detecta_formula_apos_espacos_a_esquerda():
    assert safe_csv_text("   =SOMA(A1:A2)") == "'   =SOMA(A1:A2)"
