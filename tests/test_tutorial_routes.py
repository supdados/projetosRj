"""Testes de integração para as rotas do tutorial (/tutorial/*)."""

import pytest

from models import Project, User, db
from tests._orgao_helpers import ensure_orgao


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _set_tutorial_active(client):
    with client.session_transaction() as sess:
        sess["tutorial_active"] = True
        sess["tutorial_section"] = "criar_projeto"


# ── Fixtures locais ────────────────────────────────────────────────────────────


@pytest.fixture
def user_with_area(app):
    with app.app_context():
        from tests._orgao_helpers import link_user_to_orgao

        u = User(
            username="tut_user", name="Tutorial User", orgao="Orgao T", is_admin=False
        )
        u.set_password("senha123")
        db.session.add(u)
        db.session.flush()
        link_user_to_orgao(u.id, "Auditoria")
        db.session.commit()
        return u.id


@pytest.fixture
def admin_user(app):
    with app.app_context():
        u = User(
            username="tut_admin", name="Tutorial Admin", orgao="Orgao T", is_admin=True
        )
        u.set_password("senha123")
        db.session.add(u)
        db.session.commit()
        return u.id


# ── Autenticação ───────────────────────────────────────────────────────────────


def test_tutorial_index_requires_login(client):
    resp = client.get("/tutorial")
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert "/login" in resp.headers["Location"]


def test_tutorial_index_accessible_when_logged_in(app, client, user_with_area):
    _login(client, user_with_area)
    resp = client.get("/tutorial")
    assert resp.status_code == 200
    assert "Tutorial" in resp.get_data(as_text=True)


# ── Start ──────────────────────────────────────────────────────────────────────


def test_tutorial_start_sets_session(app, client, user_with_area):
    _login(client, user_with_area)
    resp = client.post("/tutorial/start", data={"section": "criar_projeto"})
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("tutorial_active") is True
        assert sess.get("tutorial_section") == "criar_projeto"


def test_tutorial_start_redirects_to_dashboard_for_criar_projeto(
    app, client, user_with_area
):
    _login(client, user_with_area)
    resp = client.post("/tutorial/start", data={"section": "criar_projeto"})
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers["Location"]


def test_tutorial_start_section_needing_project_without_project_redirects_to_dashboard(
    app, client, user_with_area
):
    """Sem projeto tutorial criado, seções que precisam de projeto redirecionam ao dashboard."""
    _login(client, user_with_area)
    resp = client.post("/tutorial/start", data={"section": "criar_etapa"})
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers["Location"]


def test_tutorial_start_section_needing_project_with_session_id_redirects_to_project(
    app, client, user_with_area
):
    """Com tutorial_project_id na sessão, redireciona para o projeto do usuário."""
    _login(client, user_with_area)
    with app.app_context():
        p = Project(
            titulo="Meu Projeto Real",
            orgao_id=ensure_orgao("Auditoria").id,
            status="Vigente",
            is_tutorial=True,
        )
        db.session.add(p)
        db.session.commit()
        pid = p.id

    with client.session_transaction() as sess:
        sess["tutorial_project_id"] = pid

    resp = client.post("/tutorial/start", data={"section": "criar_etapa"})
    assert resp.status_code == 302
    assert f"/project/{pid}" in resp.headers["Location"]


def test_tutorial_start_unknown_section_falls_back_to_criar_projeto(
    app, client, user_with_area
):
    _login(client, user_with_area)
    resp = client.post("/tutorial/start", data={"section": "nao_existe"})
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers["Location"]


# ── Pause ──────────────────────────────────────────────────────────────────────


def test_tutorial_pause_clears_session_flag(app, client, user_with_area):
    _login(client, user_with_area)
    _set_tutorial_active(client)

    client.post("/tutorial/pause", headers={"X-Requested-With": "XMLHttpRequest"})
    with client.session_transaction() as sess:
        assert not sess.get("tutorial_active")


# ── Cleanup ────────────────────────────────────────────────────────────────────


def test_cleanup_deletes_tutorial_projects(app, client, user_with_area):
    _login(client, user_with_area)
    with app.app_context():
        from models import db as _db

        p = Project(
            titulo="Projeto Tutorial",
            orgao_id=ensure_orgao("Auditoria").id,
            status="Vigente",
            is_tutorial=True,
        )
        _db.session.add(p)
        _db.session.commit()
        assert Project.query.filter_by(is_tutorial=True).count() == 1

    resp = client.post("/tutorial/cleanup")
    assert resp.status_code == 302

    with app.app_context():
        assert Project.query.filter_by(is_tutorial=True).count() == 0


def test_cleanup_does_not_delete_real_projects(app, client, user_with_area):
    _login(client, user_with_area)

    with app.app_context():
        real = Project(
            titulo="Projeto Real",
            orgao_id=ensure_orgao("Auditoria").id,
            status="Vigente",
            is_tutorial=False,
        )
        db.session.add(real)
        demo = Project(
            titulo="Demo",
            orgao_id=ensure_orgao("Auditoria").id,
            status="Vigente",
            is_tutorial=True,
        )
        db.session.add(demo)
        db.session.commit()

    client.post("/tutorial/cleanup")

    with app.app_context():
        assert Project.query.filter_by(is_tutorial=False).count() >= 1
        assert Project.query.filter_by(is_tutorial=True).count() == 0


# ── Dismiss ────────────────────────────────────────────────────────────────────


def test_dismiss_sets_tutorial_visto(app, client, user_with_area):
    _login(client, user_with_area)

    with app.app_context():
        u = User.query.get(user_with_area)
        assert u.tutorial_visto is False

    client.post("/tutorial/dismiss", headers={"X-Requested-With": "XMLHttpRequest"})

    with app.app_context():
        u = User.query.get(user_with_area)
        assert u.tutorial_visto is True


# ── Flag is_tutorial no modelo ────────────────────────────────────────────────


def test_project_is_tutorial_defaults_to_false(app):
    with app.app_context():
        p = Project(titulo="Projeto Padrao", status="Vigente")
        db.session.add(p)
        db.session.flush()
        assert p.is_tutorial is False


def test_user_tutorial_visto_defaults_to_false(app):
    with app.app_context():
        u = User(username="novo", name="Novo", orgao="Org", is_admin=False)
        u.set_password("pw")
        db.session.add(u)
        db.session.flush()
        assert u.tutorial_visto is False
