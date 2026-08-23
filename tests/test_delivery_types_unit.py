"""Unidade de catalogs.delivery_types.normalize_delivery_type."""

import pytest

from catalogs.delivery_types import DELIVERY_TYPES_OPTIONS, normalize_delivery_type


def test_options_sao_a_tupla_esperada():
    assert DELIVERY_TYPES_OPTIONS == (
        "Sistema",
        "Painel",
        "Norma",
        "Instrumento de parceria",
        "Fluxo Processual",
        "Eventos",
        "Outro",
    )


def test_none_retorna_none():
    assert normalize_delivery_type(None) is None


@pytest.mark.parametrize("option", DELIVERY_TYPES_OPTIONS)
def test_match_exato(option):
    assert normalize_delivery_type(option) == option


@pytest.mark.parametrize(
    "value,expected",
    [
        ("sistema", "Sistema"),
        ("SISTEMA", "Sistema"),
        ("painél", "Painel"),
        ("instrumento de parceria", "Instrumento de parceria"),
        ("  outro  ", "Outro"),
        ("FLUXO PROCESSUAL", "Fluxo Processual"),
    ],
)
def test_match_insensivel_a_acento_e_caixa(value, expected):
    assert normalize_delivery_type(value) == expected


@pytest.mark.parametrize("value", ["", "Inválido", "Sistema X", "xyz"])
def test_valor_nao_reconhecido_retorna_none(value):
    assert normalize_delivery_type(value) is None
