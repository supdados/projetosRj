"""Unidade de text_folding.fold_text (comparação sem acento e sem caixa)."""

import pytest

from text_folding import fold_text


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Painel", "painel"),
        ("Painél", "painel"),
        ("  FLUXO Processual  ", "fluxo processual"),
        ("Inventário", "inventario"),
        ("", ""),
    ],
)
def test_remove_acento_caixa_e_espacos(value, expected):
    assert fold_text(value) == expected


def test_caracteres_nao_ascii_sem_equivalente_somem():
    assert fold_text("日本") == ""


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Fórum  de simplificação", "forum de simplificacao"),
        ("Fórum\nde\tsimplificação", "forum de simplificacao"),
        ("   ", ""),
    ],
)
def test_colapsa_whitespace_interno(value, expected):
    assert fold_text(value) == expected
