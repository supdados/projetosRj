from models import Etapa, Project, Task, db


def _client_for_user(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = user_id
    return client


def test_global_search_api_returns_grouped_payload_limits_and_has_more(app, client_user):
    with app.app_context():
        for index in range(1, 4):
            project = Project(
                titulo=f'Alvo Projeto {index}',
                area_responsavel='Auditoria',
                orgao='Orgao Busca',
                prioridade='media',
                status='Vigente',
                objetivo_id=1,
                resultado_esperado_id=1,
            )
            db.session.add(project)
            db.session.flush()
            db.session.add(
                Etapa(
                    descricao=f'Alvo Etapa {index}',
                    project_id=project.id,
                    ordem=0,
                )
            )
            db.session.add(
                Task(
                    descricao=f'Alvo Tarefa {index}',
                    status='nao_iniciada',
                    ordem=index,
                    project_id=project.id,
                    created_by_id=2,
                )
            )
        db.session.commit()

    response = client_user.get('/api/busca-global', query_string={'q': 'Alvo', 'limit': 2})
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['query'] == 'Alvo'
    assert payload['meta']['limit_per_type'] == 2
    assert payload['meta']['has_more']['projects'] is True
    assert payload['meta']['has_more']['stages'] is True
    assert payload['meta']['has_more']['tasks'] is True
    assert payload['meta']['has_more']['any'] is True

    assert payload['counts'] == {
        'projects': 2,
        'stages': 2,
        'tasks': 2,
        'total': 6,
    }

    assert payload['results']['projects'][0]['type'] == 'project'
    assert payload['results']['projects'][0]['display_title'] == f"{payload['results']['projects'][0]['url'].split('/project/')[1]}-{payload['results']['projects'][0]['title']}"
    assert payload['results']['stages'][0]['type'] == 'stage'
    assert payload['results']['tasks'][0]['type'] == 'task'
    assert payload['results']['projects'][0]['url'].startswith('/project/')
    assert payload['results']['tasks'][0]['url'].startswith('/tarefas/')


def test_global_search_api_prefers_prefix_matches_and_respects_area_scope(app, seed_data):
    with app.app_context():
        prefix_project = Project(
            titulo='Busca Especial Prefixo',
            area_responsavel='Auditoria',
            orgao='Orgao Busca',
            prioridade='media',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        contained_project = Project(
            titulo='Projeto com Busca Especial no meio',
            area_responsavel='Auditoria',
            orgao='Orgao Busca',
            prioridade='media',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        foreign_project = Project(
            titulo='Busca Especial VPD',
            area_responsavel='VPD',
            orgao='Orgao Busca',
            prioridade='media',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add_all([prefix_project, contained_project, foreign_project])
        db.session.commit()

    user_client = _client_for_user(app, seed_data['user_id'])
    admin_client = _client_for_user(app, seed_data['admin_id'])

    user_response = user_client.get('/api/busca-global', query_string={'q': 'Busca Especial'})
    assert user_response.status_code == 200
    user_payload = user_response.get_json()
    user_titles = [item['title'] for item in user_payload['results']['projects']]
    assert user_titles[0] == 'Busca Especial Prefixo'
    assert 'Busca Especial VPD' not in user_titles

    blocked_user_response = user_client.get(
        '/api/busca-global',
        query_string={'q': 'Busca Especial', 'area': 'VPD'},
    )
    assert blocked_user_response.status_code == 200
    blocked_payload = blocked_user_response.get_json()
    blocked_titles = [item['title'] for item in blocked_payload['results']['projects']]
    assert 'Busca Especial Prefixo' in blocked_titles
    assert 'Busca Especial VPD' not in blocked_titles

    admin_response = admin_client.get(
        '/api/busca-global',
        query_string={'q': 'Busca Especial', 'area': 'VPD'},
    )
    assert admin_response.status_code == 200
    admin_payload = admin_response.get_json()
    admin_titles = [item['title'] for item in admin_payload['results']['projects']]
    assert admin_titles == ['Busca Especial VPD']


def test_global_search_api_returns_empty_payload_for_short_query(client_user):
    response = client_user.get('/api/busca-global', query_string={'q': 'A'})
    assert response.status_code == 200
    payload = response.get_json()

    assert payload == {
        'query': 'A',
        'meta': {
            'limit_per_type': None,
            'has_more': {
                'projects': False,
                'stages': False,
                'tasks': False,
                'any': False,
            },
        },
        'counts': {
            'projects': 0,
            'stages': 0,
            'tasks': 0,
            'total': 0,
        },
        'results': {
            'projects': [],
            'stages': [],
            'tasks': [],
        },
    }


def test_search_page_renders_grouped_sections_and_hides_foreign_area_results(client_user, seed_data):
    response = client_user.get('/busca', query_string={'q': 'Auditoria'})
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Busca Global' in html
    assert 'search-results-section-title' in html
    assert 'Projetos' in html
    assert 'Etapas' in html
    assert 'Tarefas' in html
    assert 'Projeto Auditoria' in html
    assert 'Projeto VPD' not in html
    assert 'class="search-result-item search-result-item-square"' in html


def test_search_page_empty_state_without_query_and_without_results(client_user):
    empty_query_response = client_user.get('/busca')
    assert empty_query_response.status_code == 200
    assert 'Digite um termo para iniciar a busca.' in empty_query_response.get_data(as_text=True)

    no_results_response = client_user.get('/busca', query_string={'q': 'TermoInexistenteXYZ'})
    assert no_results_response.status_code == 200
    assert 'Nenhuma referencia encontrada para "<strong>TermoInexistenteXYZ</strong>".' in no_results_response.get_data(as_text=True)


def test_search_page_redirects_when_non_admin_forces_foreign_area(client_user):
    response = client_user.get(
        '/busca',
        query_string={'q': 'Auditoria', 'area': 'VPD'},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/busca?q=Auditoria')
