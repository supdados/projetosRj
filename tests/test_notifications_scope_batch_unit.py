"""Regressão do batch de escopo em ``_accessible_project_ids`` (Sprint 4).

O check por projeto via ``user_can_access_project`` recomputava o subtree de
órgãos (query em OrgaoClosure) a cada projeto — N+1 no GET /api/notificacoes.
"""

from flask import g

import routes.notifications as notifications_module
from models import Project, User, db
from routes.notifications import _accessible_project_ids


class FakeSubtreeResolver:
    """Substitui ``get_user_orgao_subtree_ids`` contando quantas vezes é chamado."""

    def __init__(self, subtree: set[int]):
        self.subtree = subtree
        self.calls = 0

    def __call__(self, user) -> set[int]:
        self.calls += 1
        return self.subtree


def _project_without_orgao() -> Project:
    project = Project(
        titulo="Projeto sem órgão",
        orgao_id=None,
        status="Vigente",
        objetivo_id=1,
        resultado_esperado_id=1,
    )
    db.session.add(project)
    db.session.flush()
    return project


def test_non_admin_scope_matches_user_can_access_project(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        orphan = _project_without_orgao()
        requested = {
            seed_data["project_id"],
            seed_data["foreign_project_id"],
            orphan.id,
        }
        assert _accessible_project_ids(requested) == {seed_data["project_id"]}


def test_admin_sees_all_existing_projects(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["admin_id"])
        requested = {seed_data["project_id"], seed_data["foreign_project_id"], 999_999}
        assert _accessible_project_ids(requested) == {
            seed_data["project_id"],
            seed_data["foreign_project_id"],
        }


def test_subtree_resolved_once_for_many_projects(app, seed_data, monkeypatch):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        resolver = FakeSubtreeResolver({seed_data["auditoria_orgao_id"]})
        monkeypatch.setattr(
            notifications_module, "get_user_orgao_subtree_ids", resolver
        )
        result = _accessible_project_ids(
            {
                seed_data["project_id"],
                seed_data["project_complete_id"],
                seed_data["foreign_project_id"],
            }
        )
        assert result == {seed_data["project_id"], seed_data["project_complete_id"]}
        assert resolver.calls == 1


def test_empty_input_short_circuits_without_queries(app, seed_data, monkeypatch):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        resolver = FakeSubtreeResolver(set())
        monkeypatch.setattr(
            notifications_module, "get_user_orgao_subtree_ids", resolver
        )
        assert _accessible_project_ids(set()) == set()
        assert resolver.calls == 0
