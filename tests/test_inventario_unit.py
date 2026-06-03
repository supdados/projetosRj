"""Testes unitários para catalogs/inventario.py.

Funções puras de regra de negócio (sem Flask/DB): definem em quais órgãos (por
sigla) o projeto especial "Inventário" é elegível e saneiam valores forjados.
"""

import pytest

from catalogs.inventario import (
    INVENTARIO_ORGAO_SIGLAS,
    orgao_allows_inventario,
    sanitize_special_project_for_orgao,
)


@pytest.mark.parametrize("sigla", list(INVENTARIO_ORGAO_SIGLAS))
def test_listed_orgaos_allow_inventario(sigla):
    assert orgao_allows_inventario(sigla) is True


@pytest.mark.parametrize("sigla", ["vpd", "Vpd", "  PRODER  "])
def test_membership_is_case_and_space_insensitive(sigla):
    assert orgao_allows_inventario(sigla) is True


@pytest.mark.parametrize("sigla", ["Auditoria", "CHEGAB", "SUPDADOS", "VP", "DIRG"])
def test_other_orgaos_do_not_allow_inventario(sigla):
    assert orgao_allows_inventario(sigla) is False


@pytest.mark.parametrize("sigla", [None, "", "   "])
def test_empty_orgao_does_not_allow_inventario(sigla):
    assert orgao_allows_inventario(sigla) is False


def test_sanitize_nullifies_inventario_for_ineligible_orgao():
    assert sanitize_special_project_for_orgao("Inventário", "Auditoria") is None
    assert sanitize_special_project_for_orgao("Inventário", None) is None


def test_sanitize_keeps_inventario_for_eligible_orgao():
    assert sanitize_special_project_for_orgao("Inventário", "VPD") == "Inventário"
    assert sanitize_special_project_for_orgao("Inventário", "vpd") == "Inventário"


@pytest.mark.parametrize("special", ["ABEP", "TCE", None, ""])
def test_sanitize_passes_other_values_unchanged(special):
    # Valores diferentes de "Inventário" nunca são afetados, independente do órgão.
    assert sanitize_special_project_for_orgao(special, "Auditoria") == special
    assert sanitize_special_project_for_orgao(special, "VPD") == special
