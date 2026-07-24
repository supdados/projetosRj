"""Unitários de ``services/project_custom_links.py`` — persistência da coleção.

Molde de ``tests/test_sei_process_unit.py``: substituição por posição, esvaziar
via delete-orphan, corte em 3 itens e propagação da validação de URL/rótulo.
"""

from __future__ import annotations

import pytest

from models import Project, ProjectCustomLink, db
from services.link_validation import LinkValidationError
from services.project_custom_links import (
    parse_custom_links_payload,
    replace_project_custom_links,
)


def _load_project(seed_data) -> Project:
    return db.session.get(Project, seed_data["project_id"])


def test_replace_persists_links_in_order(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)

        old, new = replace_project_custom_links(
            project,
            [
                {"label": "Painel BI", "url": "https://gov.br/painel"},
                {"label": "Drive", "url": "drive.google.com/x"},
            ],
        )
        db.session.commit()

        assert old == []
        assert new == [
            {"label": "Painel BI", "url": "https://gov.br/painel"},
            {"label": "Drive", "url": "https://drive.google.com/x"},
        ]
        stored = [(row.label, row.url, row.ordem) for row in project.custom_links]
        assert stored == [
            ("Painel BI", "https://gov.br/painel", 0),
            ("Drive", "https://drive.google.com/x", 1),
        ]


def test_replace_is_noop_when_unchanged(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        replace_project_custom_links(
            project, [{"label": "Painel", "url": "https://gov.br"}]
        )
        db.session.commit()
        original_ids = [row.id for row in project.custom_links]

        old, new = replace_project_custom_links(
            project, [{"label": "  Painel ", "url": "gov.br"}]
        )
        db.session.commit()

        assert old == new == [{"label": "Painel", "url": "https://gov.br"}]
        assert [row.id for row in project.custom_links] == original_ids


def test_replace_with_empty_list_deletes_orphans(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        replace_project_custom_links(
            project, [{"label": "Painel", "url": "https://gov.br"}]
        )
        db.session.commit()

        replace_project_custom_links(project, [])
        db.session.commit()

        assert project.custom_links == []
        assert ProjectCustomLink.query.filter_by(project_id=project.id).count() == 0


def test_replace_caps_at_three_links(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)

        _, new = replace_project_custom_links(
            project,
            [
                {"label": "A", "url": "https://gov.br/a"},
                {"label": "B", "url": "https://gov.br/b"},
                {"label": "C", "url": "https://gov.br/c"},
                {"label": "D", "url": "https://gov.br/d"},
            ],
        )
        db.session.commit()

        assert [link["label"] for link in new] == ["A", "B", "C"]
        assert ProjectCustomLink.query.filter_by(project_id=project.id).count() == 3


def test_replace_reuses_rows_by_position(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        replace_project_custom_links(
            project,
            [
                {"label": "A", "url": "https://gov.br/a"},
                {"label": "B", "url": "https://gov.br/b"},
            ],
        )
        db.session.commit()
        ids_before = [row.id for row in project.custom_links]

        replace_project_custom_links(
            project,
            [
                {"label": "C", "url": "https://gov.br/c"},
                {"label": "D", "url": "https://gov.br/d"},
            ],
        )
        db.session.commit()

        assert [row.label for row in project.custom_links] == ["C", "D"]
        assert [row.id for row in project.custom_links] == ids_before


def test_replace_propagates_url_validation_error(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        with pytest.raises(LinkValidationError):
            replace_project_custom_links(
                project, [{"label": "Malicioso", "url": "javascript:alert(1)"}]
            )


def test_replace_propagates_empty_label_error(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        with pytest.raises(LinkValidationError):
            replace_project_custom_links(
                project, [{"label": "  ", "url": "https://gov.br"}]
            )


def test_replace_rejects_link_without_url(app, seed_data):
    with app.app_context():
        project = _load_project(seed_data)
        with pytest.raises(LinkValidationError):
            replace_project_custom_links(project, [{"label": "Sem URL", "url": ""}])


# ---------------------------------------------------------------------------
# parse_custom_links_payload (forma do payload, compartilhado criação/inline)
# ---------------------------------------------------------------------------


def test_parse_payload_none_returns_empty():
    assert parse_custom_links_payload(None) == []


@pytest.mark.parametrize("raw", ["x", {"label": "a", "url": "b"}, 7])
def test_parse_payload_rejects_non_list(raw):
    with pytest.raises(LinkValidationError):
        parse_custom_links_payload(raw)


def test_parse_payload_rejects_over_cap():
    entries = [{"label": f"L{i}", "url": "https://gov.br"} for i in range(4)]
    with pytest.raises(LinkValidationError):
        parse_custom_links_payload(entries)


def test_parse_payload_rejects_non_dict_entry():
    with pytest.raises(LinkValidationError):
        parse_custom_links_payload(["https://gov.br"])


def test_parse_payload_coerces_missing_keys():
    assert parse_custom_links_payload([{}]) == [{"label": "", "url": None}]
