"""Testes de integração para as rotas do tutorial (/tutorial/*)."""

import pytest

from models import Project, User, db


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['user_id'] = user_id


def _set_tutorial_active(client):
    with client.session_transaction() as sess:
        sess['tutorial_active'] = True
        sess['tutorial_section'] = 'criar_projeto'


# ── Fixtures locais ────────────────────────────────────────────────────────────


@pytest.fixture
def user_with_area(app):
    with app.app_context():
        from models import UserArea
        u = User(username='tut_user', name='Tutorial User', orgao='Orgao T', is_admin=False)
        u.set_password('senha123')
        db.session.add(u)
        db.session.flush()
        db.session.add(UserArea(user_id=u.id, area='Auditoria'))
        db.session.commit()
        return u.id


@pytest.fixture
def admin_user(app):
    with app.app_context():
        u = User(username='tut_admin', name='Tutorial Admin', orgao='Orgao T', is_admin=True)
        u.set_password('senha123')
        db.session.add(u)
        db.session.commit()
        return u.id


# ── Autenticação ───────────────────────────────────────────────────────────────


def test_tutorial_index_requires_login(client):
    resp = client.get('/tutorial')
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert '/login' in resp.headers['Location']


def test_tutorial_index_accessible_when_logged_in(app, client, user_with_area):
    _login(client, user_with_area)
    resp = client.get('/tutorial')
    assert resp.status_code == 200
    assert 'Tutorial' in resp.get_data(as_text=True)


# ── Start ──────────────────────────────────────────────────────────────────────


def test_tutorial_start_sets_session(app, client, user_with_area):
    _login(client, user_with_area)
    resp = client.post('/tutorial/start', data={'section': 'criar_projeto'})
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('tutorial_active') is True
        assert sess.get('tutorial_section') == 'criar_projeto'


def test_tutorial_start_redirects_to_dashboard_for_criar_projeto(app, client, user_with_area):
    _login(client, user_with_area)
    resp = client.post('/tutorial/start', data={'section': 'criar_projeto'})
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_tutorial_start_creates_demo_project_for_section_needing_project(app, client, user_with_area):
    _login(client, user_with_area)
    with app.app_context():
        count_before = Project.query.filter_by(is_tutorial=True).count()

    resp = client.post('/tutorial/start', data={'section': 'criar_etapa'})
    assert resp.status_code == 302

    with app.app_context():
        count_after = Project.query.filter_by(is_tutorial=True).count()
    assert count_after == count_before + 1


def test_tutorial_start_reuses_existing_demo_project(app, client, user_with_area):
    _login(client, user_with_area)
    # Primeira chamada cria o projeto
    client.post('/tutorial/start', data={'section': 'criar_etapa'})
    # Segunda chamada deve reutilizar, não criar novo
    client.post('/tutorial/start', data={'section': 'criar_etapa'})

    with app.app_context():
        count = Project.query.filter_by(is_tutorial=True).count()
    assert count == 1


def test_tutorial_start_unknown_section_falls_back_to_criar_projeto(app, client, user_with_area):
    _login(client, user_with_area)
    resp = client.post('/tutorial/start', data={'section': 'nao_existe'})
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


# ── Pause ──────────────────────────────────────────────────────────────────────


def test_tutorial_pause_clears_session_flag(app, client, user_with_area):
    _login(client, user_with_area)
    _set_tutorial_active(client)

    client.post('/tutorial/pause', headers={'X-Requested-With': 'XMLHttpRequest'})
    with client.session_transaction() as sess:
        assert not sess.get('tutorial_active')


# ── Cleanup ────────────────────────────────────────────────────────────────────


def test_cleanup_deletes_tutorial_projects(app, client, user_with_area):
    _login(client, user_with_area)
    # Cria projeto de demo via start
    client.post('/tutorial/start', data={'section': 'criar_etapa'})

    with app.app_context():
        assert Project.query.filter_by(is_tutorial=True).count() == 1

    resp = client.post('/tutorial/cleanup')
    assert resp.status_code == 302

    with app.app_context():
        assert Project.query.filter_by(is_tutorial=True).count() == 0


def test_cleanup_does_not_delete_real_projects(app, client, user_with_area):
    _login(client, user_with_area)

    with app.app_context():
        real = Project(titulo='Projeto Real', area_responsavel='Auditoria', status='Vigente', is_tutorial=False)
        db.session.add(real)
        demo = Project(titulo='Demo', area_responsavel='Auditoria', status='Vigente', is_tutorial=True)
        db.session.add(demo)
        db.session.commit()

    client.post('/tutorial/cleanup')

    with app.app_context():
        assert Project.query.filter_by(is_tutorial=False).count() >= 1
        assert Project.query.filter_by(is_tutorial=True).count() == 0


# ── Dismiss ────────────────────────────────────────────────────────────────────


def test_dismiss_sets_tutorial_visto(app, client, user_with_area):
    _login(client, user_with_area)

    with app.app_context():
        u = User.query.get(user_with_area)
        assert u.tutorial_visto is False

    client.post('/tutorial/dismiss', headers={'X-Requested-With': 'XMLHttpRequest'})

    with app.app_context():
        u = User.query.get(user_with_area)
        assert u.tutorial_visto is True


# ── Flag is_tutorial no modelo ────────────────────────────────────────────────


def test_project_is_tutorial_defaults_to_false(app):
    with app.app_context():
        p = Project(titulo='Projeto Padrao', status='Vigente')
        db.session.add(p)
        db.session.flush()
        assert p.is_tutorial is False


def test_user_tutorial_visto_defaults_to_false(app):
    with app.app_context():
        u = User(username='novo', name='Novo', orgao='Org', is_admin=False)
        u.set_password('pw')
        db.session.add(u)
        db.session.flush()
        assert u.tutorial_visto is False
