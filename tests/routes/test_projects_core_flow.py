import datetime

from abep_catalog import ABEP_INDICADORES_OPTIONS
from models import Etapa, Indicador, IndicadorProjeto, Project, ProjectHistory, db


def _valid_indicator_ids():
    indicator_ids = [item.id for item in Indicador.query.filter_by(resultado_esperado_id=1).order_by(Indicador.id.asc()).all()]
    assert indicator_ids
    return indicator_ids


def test_projects_list_defaults_to_vigente_and_current_user_area(app, client_user):
    with app.app_context():
        db.session.add(
            Project(
                titulo='Projeto Auditoria Finalizado',
                area_responsavel='Auditoria',
                orgao='Orgao Finalizado',
                prioridade='media',
                status='Finalizado',
                objetivo_id=1,
                resultado_esperado_id=1,
            )
        )
        db.session.commit()

    response = client_user.get('/projects')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Projeto Auditoria' in html
    assert 'Projeto VPD' not in html
    assert 'Projeto Auditoria Finalizado' not in html


def test_projects_list_applies_admin_advanced_filters(app, client_admin):
    abep_value = ABEP_INDICADORES_OPTIONS[0]['value']

    with app.app_context():
        db.session.add_all(
            [
                Project(
                    titulo='Projeto Painel ABEP',
                    area_responsavel='VPD',
                    orgao='Orgao Filtro',
                    prioridade='alta',
                    status='Vigente',
                    objetivo_id=1,
                    resultado_esperado_id=1,
                    delivery_type='Painel',
                    abep_indicator=abep_value,
                ),
                Project(
                    titulo='Projeto Norma ABEP',
                    area_responsavel='VPD',
                    orgao='Orgao Filtro',
                    prioridade='alta',
                    status='Vigente',
                    objetivo_id=1,
                    resultado_esperado_id=1,
                    delivery_type='Norma',
                    abep_indicator=abep_value,
                ),
            ]
        )
        db.session.commit()

    response = client_admin.get(
        '/projects',
        query_string={
            'area': 'VPD',
            'status': 'Vigente',
            'delivery_type': 'Painel',
            'abep_indicator': abep_value,
            'objetivo': '1',
            'search': 'Painel',
        },
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Projeto Painel ABEP' in html
    assert 'Projeto Norma ABEP' not in html
    assert 'Projeto Auditoria' not in html


def test_add_project_creates_stages_indicators_and_history(app, client_user):
    abep_value = ABEP_INDICADORES_OPTIONS[0]['value']

    response = client_user.post(
        '/add_project',
        data={
            'project_titulo': 'Projeto Criado Completo',
            'project_area_responsavel': 'Auditoria',
            'project_orgao': 'Orgao Novo',
            'project_prioridade': 'media',
            'project_objetivo': '1',
            'project_resultado': '1',
            'project_indicadores': ['1'],
            'project_observacao': 'Observacao detalhada',
            'project_special_project': 'ABEP',
            'project_sei_process': 'SEI-123456/654321/2026',
            'project_short_description': 'Descricao curta',
            'project_delivery_type': 'Sistema',
            'project_abep_indicator': abep_value,
            'project_github_link': 'https://github.com/exemplo/projeto',
            'project_documentation_link': 'https://docs.example.com/projeto',
            'etapa_descricao': ['Etapa 1', 'Etapa 2'],
            'etapa_duration': ['2', '3'],
            'project_start_date': '2026-03-10',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        project = Project.query.filter_by(titulo='Projeto Criado Completo').first()
        assert project is not None
        assert project.area_responsavel == 'Auditoria'
        assert project.delivery_type == 'Sistema'
        assert project.abep_indicator == abep_value
        assert project.special_project == 'ABEP'

        etapas = Etapa.query.filter_by(project_id=project.id).order_by(Etapa.ordem.asc()).all()
        assert [etapa.descricao for etapa in etapas] == ['Etapa 1', 'Etapa 2']
        assert etapas[0].data_inicio == datetime.date(2026, 3, 10)
        assert etapas[0].data_fim == datetime.date(2026, 3, 11)
        assert etapas[1].data_inicio == datetime.date(2026, 3, 12)
        assert etapas[1].data_fim == datetime.date(2026, 3, 14)

        assert IndicadorProjeto.query.filter_by(project_id=project.id).count() == 1
        history = (
            ProjectHistory.query
            .filter_by(project_id=project.id, action_type='create')
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert 'Criou o projeto "Projeto Criado Completo"' in history.action_description


def test_edit_project_updates_fields_and_history(app, client_user, seed_data):
    with app.app_context():
        indicator_ids = _valid_indicator_ids()
        selected_indicator = str(indicator_ids[-1])

    response = client_user.post(
        f"/project/{seed_data['project_id']}/edit",
        data={
            'project_titulo': 'Projeto Auditoria Editado',
            'project_orgao': 'Orgao Editado',
            'project_area_responsavel': 'Auditoria',
            'project_prioridade': 'urgente',
            'project_status': 'Suspenso',
            'project_special_project': 'TCE',
            'project_sei_process': 'SEI-123456/654321/2026',
            'project_short_description': 'Resumo novo',
            'project_delivery_type': 'Painel',
            'project_abep_indicator': ABEP_INDICADORES_OPTIONS[1]['value'],
            'project_github_link': 'https://github.com/exemplo/editado',
            'project_documentation_link': 'https://docs.example.com/editado',
            'project_objetivo': '1',
            'project_resultado': '1',
            'project_indicadores': [selected_indicator],
            'project_observacao': 'Observacao atualizada',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        project = db.session.get(Project, seed_data['project_id'])
        assert project is not None
        assert project.titulo == 'Projeto Auditoria Editado'
        assert project.orgao == 'Orgao Editado'
        assert project.prioridade == 'urgente'
        assert project.status == 'Suspenso'
        assert project.special_project == 'TCE'
        assert project.delivery_type == 'Painel'
        assert project.abep_indicator == ABEP_INDICADORES_OPTIONS[1]['value']

        indicator_ids = [
            row.indicador_id
            for row in IndicadorProjeto.query.filter_by(project_id=project.id).order_by(IndicadorProjeto.id.asc()).all()
        ]
        assert indicator_ids == [int(selected_indicator)]

        history = (
            ProjectHistory.query
            .filter_by(project_id=project.id, action_type='edit')
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert 'Projeto Auditoria Editado' in history.action_description


def test_project_edit_data_returns_goal_payload(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}/edit_data")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload['success'] is True
    assert payload['is_admin'] is False
    assert payload['indicadores_do_projeto'] == [1]
    assert any(item['id'] == 1 for item in payload['objetivos'])
    assert 'Auditoria' in payload['areas_responsaveis']


def test_update_project_inline_updates_abep_goal_and_history(app, client_user, seed_data):
    with app.app_context():
        indicator_ids = _valid_indicator_ids()
        selected_indicator = indicator_ids[-1]

    response = client_user.post(
        f"/project/{seed_data['project_id']}/update_inline",
        json={
            'titulo': 'Projeto Inline Atualizado',
            'orgao': 'Orgao Inline',
            'prioridade': 'baixa',
            'abep_indicator': ABEP_INDICADORES_OPTIONS[2]['value'],
            'objetivo_id': 1,
            'resultado_esperado_id': 1,
            'indicadores_ids': [selected_indicator],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    with app.app_context():
        project = db.session.get(Project, seed_data['project_id'])
        assert project is not None
        assert project.titulo == 'Projeto Inline Atualizado'
        assert project.orgao == 'Orgao Inline'
        assert project.prioridade == 'baixa'
        assert project.abep_indicator == ABEP_INDICADORES_OPTIONS[2]['value']

        indicator_ids = [
            row.indicador_id
            for row in IndicadorProjeto.query.filter_by(project_id=project.id).order_by(IndicadorProjeto.id.asc()).all()
        ]
        assert indicator_ids == [selected_indicator]

        history = (
            ProjectHistory.query
            .filter_by(project_id=project.id, action_type='edit')
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert 'Editou o projeto (inline)' in history.action_description


def test_update_project_inline_rejects_invalid_area(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/update_inline",
        json={'area_responsavel': 'Area Inexistente'},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert 'área selecionada é inválida' in payload['message'].lower()


def test_concluir_project_json_requires_all_stages_completed(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/concluir",
        headers={'Accept': 'application/json'},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert 'Todas as etapas devem estar iniciadas e concluídas' in payload['message']


def test_concluir_project_json_finalizes_project_and_logs_history(app, client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/concluir",
        headers={'Accept': 'application/json'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True

    with app.app_context():
        project = db.session.get(Project, seed_data['project_complete_id'])
        assert project is not None
        assert project.status == 'Finalizado'

        history = (
            ProjectHistory.query
            .filter_by(project_id=project.id, action_type='finalize')
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert 'Concluiu o projeto' in history.action_description


def test_delete_project_ajax_removes_project_from_database(app, client_user):
    with app.app_context():
        project = Project(
            titulo='Projeto Para Excluir',
            area_responsavel='Auditoria',
            orgao='Orgao Delete',
            prioridade='baixa',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client_user.post(
        f'/project/{project_id}/delete',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ok'] is True

    with app.app_context():
        assert db.session.get(Project, project_id) is None

