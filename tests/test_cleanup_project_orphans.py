import json

import pytest
from flask import Flask

from models import (
    ProjectCollection,
    ProjectCollectionItem,
    ProjectMember,
    StageTemplateUsage,
    db,
)
from scripts.migrations.cleanup_project_orphans import cleanup_project_orphans, main


@pytest.fixture
def orphan_project_children(app, seed_data) -> None:
    with app.app_context():
        collection = ProjectCollection(
            owner_user_id=seed_data["user_id"], nome="Preservar"
        )
        db.session.add(collection)
        db.session.flush()
        for project_id in (seed_data["project_id"], 999999):
            db.session.add_all(
                [
                    ProjectMember(
                        project_id=project_id,
                        user_id=seed_data["outsider_id"],
                        granted_by_id=seed_data["user_id"],
                        papel="editor",
                    ),
                    ProjectCollectionItem(
                        collection_id=collection.id, project_id=project_id
                    ),
                    StageTemplateUsage(
                        project_id=project_id,
                        template_id=seed_data["template_id"],
                        source="create",
                    ),
                ]
            )
        db.session.commit()


def test_cleanup_dry_run_apply_and_idempotence(
    app, orphan_project_children, seed_data
) -> None:
    with app.app_context():
        expected = {
            "project_member": 1,
            "project_collection_item": 1,
            "stage_template_usage": 1,
        }
        assert cleanup_project_orphans(db.session()) == expected
        assert cleanup_project_orphans(db.session()) == expected
        assert cleanup_project_orphans(db.session(), apply=True) == expected
        assert cleanup_project_orphans(db.session(), apply=True) == dict.fromkeys(
            expected, 0
        )
        for model in (ProjectMember, ProjectCollectionItem, StageTemplateUsage):
            assert model.query.count() == 1
            assert model.query.one().project_id == seed_data["project_id"]


class CleanupCommitFailure:
    def __call__(self) -> None:
        raise RuntimeError("Falha de commit simulada")


def test_cleanup_rolls_back_every_table(
    app, orphan_project_children, monkeypatch
) -> None:
    with app.app_context():
        session = db.session()
        monkeypatch.setattr(session, "commit", CleanupCommitFailure())
        with pytest.raises(RuntimeError, match="Falha de commit"):
            cleanup_project_orphans(session, apply=True)
        assert all(
            model.query.count() == 2
            for model in (ProjectMember, ProjectCollectionItem, StageTemplateUsage)
        )


class TestAppFactory:
    __test__ = False

    def __init__(self, app: Flask) -> None:
        self.app = app

    def __call__(self, config: dict[str, bool]) -> Flask:
        return self.app


def test_cli_defaults_to_inventory_and_applies_only_with_flag(
    app, orphan_project_children, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("app.create_app", TestAppFactory(app))
    assert main([]) == 0
    inventory = json.loads(capsys.readouterr().out)
    assert inventory["applied"] is False
    assert main(["--apply"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["applied"] is True
    assert applied["orphans"] == inventory["orphans"]
