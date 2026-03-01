from models import Project, ProjectHistory, db


def test_project_history_page_renders_filters_and_category_markers(app, client_user, seed_data):
    with app.app_context():
        db.session.add_all(
            [
                ProjectHistory(
                    project_id=seed_data['project_id'],
                    user_id=seed_data['user_id'],
                    action_type='edit',
                    action_description='Projeto atualizado no teste',
                ),
                ProjectHistory(
                    project_id=seed_data['project_id'],
                    user_id=seed_data['user_id'],
                    action_type='add_etapa',
                    action_description='Etapa adicionada no teste',
                ),
                ProjectHistory(
                    project_id=seed_data['project_id'],
                    user_id=seed_data['user_id'],
                    action_type='migration',
                    action_description='Migração registrada no teste',
                ),
            ]
        )
        db.session.commit()

    response = client_user.get(f"/project/{seed_data['project_id']}/history")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'id="historySearch"',
        'id="historyTypeFilter"',
        'id="historyPeriodFilter"',
        'id="counterTotal"',
        'id="counterProject"',
        'id="counterStage"',
        'id="counterSystem"',
        'id="historyEntriesList"',
        'id="historyNoResults"',
    ]

    for hook in required_hooks:
        assert hook in html

    assert 'data-category="project"' in html
    assert 'data-category="stage"' in html
    assert 'data-category="system"' in html
    assert 'Criação de projeto' not in html
    assert 'Edição de projeto' in html
    assert 'Nova etapa' in html
    assert 'Evento de sistema' in html


def test_project_history_empty_state_for_project_without_entries(app, client_user):
    with app.app_context():
        project = Project(
            titulo='Projeto Sem Historico',
            area_responsavel='Auditoria',
            orgao='Orgao Limpo',
            prioridade='media',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client_user.get(f'/project/{project_id}/history')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Nenhuma ação registrada ainda' in html
    assert 'O histórico será exibido aqui à medida que o projeto for atualizado.' in html
