"""Unidade de catalogs.priorities.normalize_priority."""

import pytest

from catalogs.priorities import PRIORITY_OPTIONS, normalize_priority


def test_options_sao_a_tupla_esperada():
    assert PRIORITY_OPTIONS == ("baixa", "media", "alta", "urgente")


def test_none_retorna_none():
    assert normalize_priority(None) is None


@pytest.mark.parametrize("option", PRIORITY_OPTIONS)
def test_match_exato(option):
    assert normalize_priority(option) == option


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Urgente", "urgente"),
        ("URGENTE", "urgente"),
        ("Média", "media"),
        ("media ", "media"),
        ("  baixa  ", "baixa"),
        ("ALTA", "alta"),
    ],
)
def test_match_insensivel_a_acento_caixa_e_espaco(value, expected):
    assert normalize_priority(value) == expected


@pytest.mark.parametrize("value", ["", "inválida", "baixa demais", "xyz"])
def test_valor_nao_reconhecido_retorna_none(value):
    assert normalize_priority(value) is None
