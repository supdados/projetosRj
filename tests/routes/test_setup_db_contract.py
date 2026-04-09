from sqlalchemy import inspect

from models import db


def test_setup_db_requires_admin(client):
    response = client.get('/setup_db')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_setup_db_json_returns_status_details_and_sync_summary(app, client_admin):
    response = client_admin.get('/setup_db', headers={'Accept': 'application/json'})

    assert response.status_code == 200
    payload = response.get_json()

    assert payload['status'] == 'success'
    assert payload['detalhes']['tabela_project_existe'] is True
    assert payload['detalhes']['tabela_user_existe'] is True
    assert payload['detalhes']['tabelas_criadas'] is False
    assert payload['detalhes']['abep_indicator_column'] == 'exists'
    assert payload['detalhes']['ambiente'] == 'Desenvolvimento Local'
    assert 'banco_de_dados' not in payload['detalhes']

    sync_summary = payload['detalhes']['catalogo_objetivos_sync']
    assert isinstance(sync_summary, dict)
    assert set(sync_summary.keys()) == {
        'objetivos_created',
        'objetivos_updated',
        'resultados_created',
        'resultados_updated',
        'indicadores_created',
        'indicadores_updated',
    }


def test_setup_db_force_true_keeps_schema_available_and_returns_html(app, client_admin):
    response = client_admin.get('/setup_db?force=true')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<h1>Status do Banco de Dados</h1>' in html
    assert 'Banco de dados configurado. Tabelas faltantes (re)criadas.' in html
    assert 'Forçar criação de tabelas faltantes' in html
    assert '/setup_db?force=true' in html
    assert 'mysql://' not in html
    assert 'sqlite://' not in html

    with app.app_context():
        inspector = inspect(db.engine)
        project_columns = {column['name'] for column in inspector.get_columns('project')}
        assert 'abep_indicator' in project_columns
