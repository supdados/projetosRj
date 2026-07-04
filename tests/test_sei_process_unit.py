"""Unitários de ``services/sei_process.py`` — normalização e persistência.

Fixam o contrato de tolerância da entrada: prefixo "SEI-" opcional em qualquer
caixa/espaçamento (colar "SEI-380001/000664/2026" NÃO dá erro), texto legado
sem dígito inicial passa verbatim e a única rejeição dura é o estouro do limite
da coluna.
"""

from __future__ import annotations

import pytest

from models import Project, ProjectSeiProcess, db
from services.sei_process import (
    SEI_NUMBER_MAX_LENGTH,
    SeiProcessValidationError,
    normalize_sei_list,
    normalize_sei_number,
    normalize_sei_number_or_raw,
    replace_project_sei_numbers,
)

# ---------------------------------------------------------------------------
# normalize_sei_number
# ---------------------------------------------------------------------------


def test_normalize_adds_prefix_to_bare_number():
    assert normalize_sei_number("380001/000664/2026") == "SEI-380001/000664/2026"


@pytest.mark.parametrize(
    "raw",
    [
        "SEI-380001/000664/2026",
        "sei-380001/000664/2026",
        "SEI - 380001/000664/2026",
        "sei 380001/000664/2026",
        "  SEI-380001/000664/2026  ",
    ],
)
def test_normalize_accepts_prefix_case_and_spacing_variants(raw):
    assert normalize_sei_number(raw) == "SEI-380001/000664/2026"


def test_normalize_is_idempotent_on_canonical_value():
    canonical = "SEI-380001/000664/2026"
    assert normalize_sei_number(canonical) == canonical


def test_normalize_collapses_internal_whitespace():
    assert (
        normalize_sei_number("380001 / 000664 / 2026") == "SEI-380001 / 000664 / 2026"
    )


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_normalize_empty_input_returns_none(raw):
    assert normalize_sei_number(raw) is None


def test_normalize_free_text_without_leading_digit_passes_verbatim():
    assert normalize_sei_number("processo antigo") == "processo antigo"


def test_normalize_rejects_value_over_column_limit():
    oversized = "9" * (SEI_NUMBER_MAX_LENGTH + 1)
    with pytest.raises(SeiProcessValidationError) as excinfo:
        normalize_sei_number(oversized)
    message = str(excinfo.value)
    assert oversized in message
    assert "SEI-380001/000664/2026" in message


def test_normalize_or_raw_truncates_oversized_legacy_value():
    oversized = "x" * (SEI_NUMBER_MAX_LENGTH + 10)
    result = normalize_sei_number_or_raw(oversized)
    assert result == "x" * SEI_NUMBER_MAX_LENGTH


# ---------------------------------------------------------------------------
# normalize_sei_list
# ---------------------------------------------------------------------------


def test_normalize_list_dedupes_case_insensitive_keeping_first():
    result = normalize_sei_list(
        ["SEI-000001/2026", "sei-000001/2026", "000001/2026", "SEI-000002/2026"]
    )
    assert result == ["SEI-000001/2026", "SEI-000002/2026"]


def test_normalize_list_drops_empty_items():
    assert normalize_sei_list(["", "  ", "000001/2026"]) == ["SEI-000001/2026"]


# ---------------------------------------------------------------------------
# replace_project_sei_numbers
# ---------------------------------------------------------------------------


def _load_project(seed_data) -> Project:
    return db.session.get(Project, seed_data["project_id"])


def test_replace_persists_normalized_numbers_in_order(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)

        old, new = replace_project_sei_numbers(
            project, ["380001/000664/2026", "SEI-380002/000001/2026"]
        )
        db.session.commit()

        assert old == []
        assert new == ["SEI-380001/000664/2026", "SEI-380002/000001/2026"]
        stored = [(item.numero, item.ordem) for item in project.sei_processes]
        assert stored == [
            ("SEI-380001/000664/2026", 0),
            ("SEI-380002/000001/2026", 1),
        ]


def test_replace_is_noop_when_list_is_unchanged(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        replace_project_sei_numbers(project, ["SEI-000001/2026"])
        db.session.commit()
        original_ids = [item.id for item in project.sei_processes]

        old, new = replace_project_sei_numbers(project, ["sei- 000001/2026"])
        db.session.commit()

        assert old == new == ["SEI-000001/2026"]
        assert [item.id for item in project.sei_processes] == original_ids


def test_replace_removing_first_number_keeps_the_rest(app, seed_data):
    """Regressão: número mantido entre listas NÃO pode virar delete+insert
    (o flush insere antes de deletar e violaria a UNIQUE(project_id, numero))."""
    with app.app_context():
        project = _load_project(seed_data)
        replace_project_sei_numbers(project, ["SEI-000001/2026", "SEI-000002/2026"])
        db.session.commit()
        kept_id = project.sei_processes[1].id

        replace_project_sei_numbers(project, ["SEI-000002/2026"])
        db.session.commit()

        assert [
            (item.id, item.numero, item.ordem) for item in project.sei_processes
        ] == [(kept_id, "SEI-000002/2026", 0)]


def test_replace_reorder_updates_ordem_reusing_rows(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        replace_project_sei_numbers(project, ["SEI-000001/2026", "SEI-000002/2026"])
        db.session.commit()
        ids_before = {item.numero: item.id for item in project.sei_processes}

        replace_project_sei_numbers(project, ["SEI-000002/2026", "SEI-000001/2026"])
        db.session.commit()

        assert [item.numero for item in project.sei_processes] == [
            "SEI-000002/2026",
            "SEI-000001/2026",
        ]
        assert {item.numero: item.id for item in project.sei_processes} == ids_before


def test_replace_with_empty_list_deletes_orphans(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        replace_project_sei_numbers(project, ["SEI-000001/2026"])
        db.session.commit()

        replace_project_sei_numbers(project, [])
        db.session.commit()

        assert project.sei_processes == []
        assert ProjectSeiProcess.query.filter_by(project_id=project.id).count() == 0


def test_replace_mirrors_first_number_in_legacy_column(app, seed_data):
    """Expand-contract: a coluna legada acompanha o primeiro número (rollback
    do release continua exibindo o processo em vez de vazio)."""
    with app.app_context():
        project = _load_project(seed_data)

        replace_project_sei_numbers(project, ["000002/2026", "000001/2026"])
        db.session.commit()
        assert project.sei_process == "SEI-000002/2026"

        replace_project_sei_numbers(project, [])
        db.session.commit()
        assert project.sei_process is None
