"""Backfill ``Project.sei_process`` <-> ``ProjectSeiProcess`` (idempotência).

O passo roda a cada boot via ``run_all_migrations`` com semântica
expand-contract: escalar desconhecido vira filho (legado pré-feature E edições
de instância antiga em rolling deploy) e a coluna é reescrita como ESPELHO do
primeiro filho — rollback do release continua mostrando o primeiro número.
"""

from __future__ import annotations

from models import Project, ProjectSeiProcess, db
from scripts.migrations.backfill_sei_processes import backfill_sei_processes
from services.sei_process import replace_project_sei_numbers


def _set_legacy_scalar(seed_data, value: str) -> int:
    project = db.session.get(Project, seed_data["project_id"])
    project.sei_process = value
    db.session.commit()
    return project.id


def test_backfill_normalizes_legacy_value_and_mirrors_column(app, seed_data):
    with app.app_context():
        project_id = _set_legacy_scalar(seed_data, "380001/000664/2026")

        summary = backfill_sei_processes(emit_output=False)

        assert summary == {"success": True, "migrated": 1}
        project = db.session.get(Project, project_id)
        assert [(item.numero, item.ordem) for item in project.sei_processes] == [
            ("SEI-380001/000664/2026", 0)
        ]
        assert project.sei_process == "SEI-380001/000664/2026"


def test_backfill_keeps_two_group_legacy_format_without_loss(app, seed_data):
    with app.app_context():
        project_id = _set_legacy_scalar(seed_data, "SEI-000001/2026")

        backfill_sei_processes(emit_output=False)

        project = db.session.get(Project, project_id)
        assert [item.numero for item in project.sei_processes] == ["SEI-000001/2026"]


def test_backfill_preserves_free_text_verbatim(app, seed_data):
    with app.app_context():
        project_id = _set_legacy_scalar(seed_data, "processo em papel")

        backfill_sei_processes(emit_output=False)

        project = db.session.get(Project, project_id)
        assert [item.numero for item in project.sei_processes] == ["processo em papel"]


def test_backfill_second_run_does_not_duplicate(app, seed_data):
    with app.app_context():
        project_id = _set_legacy_scalar(seed_data, "380001/000664/2026")

        backfill_sei_processes(emit_output=False)
        summary = backfill_sei_processes(emit_output=False)

        assert summary == {"success": True, "migrated": 0}
        assert ProjectSeiProcess.query.filter_by(project_id=project_id).count() == 1


def test_backfill_does_not_resurrect_numbers_removed_via_ui(app, seed_data):
    with app.app_context():
        project_id = _set_legacy_scalar(seed_data, "380001/000664/2026")
        backfill_sei_processes(emit_output=False)

        # Remoção pela UI passa por replace_project_sei_numbers, que também
        # limpa o espelho — o boot seguinte não tem o que ressuscitar.
        project = db.session.get(Project, project_id)
        replace_project_sei_numbers(project, [])
        db.session.commit()

        summary = backfill_sei_processes(emit_output=False)

        assert summary == {"success": True, "migrated": 0}
        assert db.session.get(Project, project_id).sei_processes == []


def test_backfill_absorbs_scalar_edit_from_old_instance(app, seed_data):
    """Rolling deploy: instância ANTIGA grava só a coluna; o boot seguinte
    incorpora o número como filho novo sem apagar os existentes."""
    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        replace_project_sei_numbers(project, ["SEI-000001/2026", "SEI-000002/2026"])
        # Emula o código velho: escreve direto na coluna, sem tocar nos filhos.
        project.sei_process = "999999/000001/2026"
        db.session.commit()

        summary = backfill_sei_processes(emit_output=False)

        assert summary == {"success": True, "migrated": 1}
        refreshed = db.session.get(Project, seed_data["project_id"])
        assert [item.numero for item in refreshed.sei_processes] == [
            "SEI-000001/2026",
            "SEI-000002/2026",
            "SEI-999999/000001/2026",
        ]
        assert refreshed.sei_process == "SEI-000001/2026"
