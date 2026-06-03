"""Testes unitários para catalogs/inventario.py.

Funções puras de regra de negócio (sem Flask/DB): definem em quais áreas o
projeto especial "Inventário" é elegível e saneiam valores forjados.
"""

import pytest

from catalogs.inventario import (
    INVENTARIO_AREAS,
    area_allows_inventario,
    sanitize_special_project_for_area,
)


@pytest.mark.parametrize("area", list(INVENTARIO_AREAS))
def test_listed_areas_allow_inventario(area):
    assert area_allows_inventario(area) is True


@pytest.mark.parametrize("area", ["vpd", "Vpd", "  PRODER  "])
def test_membership_is_case_and_space_insensitive(area):
    assert area_allows_inventario(area) is True


@pytest.mark.parametrize("area", ["Auditoria", "CHEGAB", "SUPDADOS", "VP", "DIRG"])
def test_other_areas_do_not_allow_inventario(area):
    assert area_allows_inventario(area) is False


@pytest.mark.parametrize("area", [None, "", "   "])
def test_empty_area_does_not_allow_inventario(area):
    assert area_allows_inventario(area) is False


def test_sanitize_nullifies_inventario_for_ineligible_area():
    assert sanitize_special_project_for_area("Inventário", "Auditoria") is None
    assert sanitize_special_project_for_area("Inventário", None) is None


def test_sanitize_keeps_inventario_for_eligible_area():
    assert sanitize_special_project_for_area("Inventário", "VPD") == "Inventário"
    assert sanitize_special_project_for_area("Inventário", "vpd") == "Inventário"


@pytest.mark.parametrize("special", ["ABEP", "TCE", None, ""])
def test_sanitize_passes_other_values_unchanged(special):
    # Valores diferentes de "Inventário" nunca são afetados, independente da área.
    assert sanitize_special_project_for_area(special, "Auditoria") == special
    assert sanitize_special_project_for_area(special, "VPD") == special
