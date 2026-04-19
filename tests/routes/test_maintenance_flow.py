"""Cobertura adicional de /setup_db e /favicon.ico em routes/maintenance.py.

Complementa tests/routes/test_setup_db_contract.py com:
  * fluxo HTML padrão (sem force) — branch "já existem"
  * recriação da coluna legada abep_indicator quando ausente
  * caminho de exceção (JSON vs HTML)
  * rota /favicon.ico — headers de cache e tipo de conteúdo
"""

from sqlalchemy import inspect, text

from models import db
from routes import maintenance


# ---------------------------------------------------------------------------
# /setup_db — fluxo HTML padrão (tabelas já existem)
# ---------------------------------------------------------------------------


def test_setup_db_default_returns_html_when_tables_already_exist(app, client_admin):
    response = client_admin.get('/setup_db')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<h1>Status do Banco de Dados</h1>' in html
    assert 'As tabelas principais já existem' in html
    # Link "forçar" é renderizado no rodapé para permitir action subsequente.
    assert 'force=true' in html


def test_setup_db_html_reports_environment_when_gae_env_absent(app, client_admin):
    response = client_admin.get('/setup_db')

    html = response.get_data(as_text=True)
    assert 'Desenvolvimento Local' in html


def test_setup_db_html_lists_existing_tables(app, client_admin):
    response = client_admin.get('/setup_db')

    html = response.get_data(as_text=True)
    # Algumas tabelas criadas pelo ensure_area_catalog_seeded / create_all.
    assert 'project' in html
    assert 'user' in html


# ---------------------------------------------------------------------------
# /setup_db — recriação da coluna legada abep_indicator
# ---------------------------------------------------------------------------


def test_setup_db_recreates_abep_indicator_column_when_dropped(app, client_admin):
    with app.app_context():
        # Simula um banco legado: recria a tabela project sem a coluna.
        db.session.execute(text('ALTER TABLE project DROP COLUMN abep_indicator'))
        db.session.commit()

        inspector = inspect(db.engine)
        columns = {col['name'] for col in inspector.get_columns('project')}
        assert 'abep_indicator' not in columns

    response = client_admin.get('/setup_db', headers={'Accept': 'application/json'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['detalhes']['abep_indicator_column'] == 'created'

    with app.app_context():
        inspector = inspect(db.engine)
        columns = {col['name'] for col in inspector.get_columns('project')}
        assert 'abep_indicator' in columns


# ---------------------------------------------------------------------------
# /setup_db — caminho de exceção
# ---------------------------------------------------------------------------


def test_setup_db_returns_error_message_when_sync_raises(app, client_admin, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError('falha simulada no sync')

    monkeypatch.setattr(maintenance, 'sync_goal_catalog_to_db', _boom)

    response = client_admin.get('/setup_db', headers={'Accept': 'application/json'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'error'
    assert 'falha simulada' in payload['mensagem']


def test_setup_db_returns_error_plain_text_when_accept_is_html(app, client_admin, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError('outra falha')

    monkeypatch.setattr(maintenance, 'sync_goal_catalog_to_db', _boom)

    response = client_admin.get('/setup_db')
    # Sem Accept JSON → payload bruto (string), sem HTML estruturado.
    body = response.get_data(as_text=True)
    assert 'outra falha' in body
    assert '<h1>' not in body


# ---------------------------------------------------------------------------
# /favicon.ico
# ---------------------------------------------------------------------------


def test_favicon_returns_icon_with_no_cache_headers(client):
    response = client.get('/favicon.ico')

    assert response.status_code == 200
    assert response.mimetype == 'image/vnd.microsoft.icon'
    assert response.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'
    assert response.headers.get('Pragma') == 'no-cache'
    assert response.headers.get('Expires') == '0'


def test_favicon_available_without_authentication(client):
    # Favicon é público: mesmo sem login, retorna 200.
    response = client.get('/favicon.ico')
    assert response.status_code == 200
