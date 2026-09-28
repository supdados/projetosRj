"""P1-01: apagar um projeto não transfere seus vínculos ao próximo ID SQLite."""

import time
from pathlib import Path

import pytest
from flask import Flask
from flask_migrate import upgrade
from sqlalchemy import text

from catalogs.objectives import sync_goal_catalog_to_db

from models import (
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    ProjectMember,
    StageTemplateUsage,
    db,
)


@pytest.fixture(params=["models", "migrations"])
def app(app, request) -> Flask:
    """Repete a reprodução com create_all e com o schema real da cadeia Alembic."""
    if request.param == "migrations":
        with app.app_context():
            db.drop_all()
            upgrade(directory=str(Path(__file__).resolve().parents[2] / "migrations"))
            sync_goal_catalog_to_db(commit=True)
    return app


@pytest.fixture
def shared_project(app, client_user, seed_data) -> int:
    response = client_user.post(
        "/api/projetos",
        json={
            "titulo": "Projeto a excluir",
            "orgao_id": seed_data["auditoria_orgao_id"],
        },
    )
    assert response.status_code == 200
    project_id = response.get_json()["data"]["id"]
    with app.app_context():
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 0
        collection = ProjectCollection(
            owner_user_id=seed_data["user_id"], nome="Compartilhada"
        )
        db.session.add(collection)
        db.session.flush()
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
                ProjectCollectionItem(
                    collection_id=collection.id, project_id=seed_data["project_id"]
                ),
                ProjectCollectionShare(
                    collection_id=collection.id,
                    user_id=seed_data["deletable_user_id"],
                    created_by_user_id=seed_data["user_id"],
                    papel="editor",
                ),
                StageTemplateUsage(
                    template_id=seed_data["template_id"],
                    project_id=project_id,
                    source="create",
                ),
            ]
        )
        db.session.commit()
    return project_id


def test_delete_removes_project_children_only(
    app, client_user, seed_data, shared_project
) -> None:
    assert client_user.delete(f"/api/projetos/{shared_project}").status_code == 200
    with app.app_context():
        assert db.session.get(Project, shared_project) is None
        assert ProjectMember.query.filter_by(project_id=shared_project).count() == 0
        assert (
            ProjectCollectionItem.query.filter_by(project_id=shared_project).count()
            == 0
        )
        assert (
            StageTemplateUsage.query.filter_by(project_id=shared_project).count() == 0
        )
        assert ProjectCollection.query.count() == 1
        assert ProjectCollectionShare.query.count() == 1
        assert (
            ProjectCollectionItem.query.filter_by(
                project_id=seed_data["project_id"]
            ).count()
            == 1
        )


@pytest.mark.parametrize("recipient", ["outsider_id", "deletable_user_id"])
def test_reused_id_has_no_old_invitation_or_collection_access(
    app, client_user, seed_data, shared_project, recipient
) -> None:
    former_recipient = app.test_client()
    with former_recipient.session_transaction() as session:
        session["user_id"] = seed_data[recipient]
        session["login_at"] = time.time()
    assert (
        former_recipient.get(f"/api/projetos/{shared_project}/detalhe").status_code
        == 200
    )
    assert client_user.delete(f"/api/projetos/{shared_project}").status_code == 200
    created = client_user.post(
        "/api/projetos",
        json={
            "titulo": "Projeto privado novo",
            "orgao_id": seed_data["auditoria_orgao_id"],
        },
    )
    assert created.status_code == 200
    new_id = created.get_json()["data"]["id"]
    assert (
        new_id == shared_project
    )  # Reproduz a reutilização, sem mascará-la com AUTOINCREMENT.
    assert former_recipient.get(f"/api/projetos/{new_id}/detalhe").status_code == 404
    assert (
        former_recipient.post(
            "/api/tarefas", json={"project": new_id, "descricao": "Escrita indevida"}
        ).status_code
        == 404
    )


class FailingProjectCommit:
    def __call__(self) -> None:
        db.session.flush()
        raise RuntimeError("Falha simulada após excluir os vínculos")


def test_failed_delete_rolls_back_project_and_children(
    app, client_user, shared_project, monkeypatch
) -> None:
    monkeypatch.setattr(db.session, "commit", FailingProjectCommit())
    assert client_user.delete(f"/api/projetos/{shared_project}").status_code == 500
    with app.app_context():
        assert db.session.get(Project, shared_project) is not None
        assert ProjectMember.query.filter_by(project_id=shared_project).count() == 1
        assert (
            ProjectCollectionItem.query.filter_by(project_id=shared_project).count()
            == 1
        )
        assert (
            StageTemplateUsage.query.filter_by(project_id=shared_project).count() == 1
        )
