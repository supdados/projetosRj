def test_project_add_modal_uses_abep_search_input(client_user):
    response = client_user.get('/projects')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="project_abep_indicator_search"' not in html
    assert 'id="project_abep_indicator_group"' not in html
    assert 'id="project_abep_indicator_input"' in html
    assert 'id="project_abep_indicator"' in html
    assert 'id="projectAbepIndicatorDropdown"' in html


def test_project_add_modal_distributes_fields_in_updated_sections(client_user):
    response = client_user.get('/projects')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    planning_start = html.index('id="projectCreateSectionPlanning"')
    goals_start = html.index('id="projectCreateSectionGoals"')
    details_start = html.index('id="projectCreateSectionDetails"')
    template_start = html.index('id="projectCreateSectionTemplate"')

    planning_html = html[planning_start:goals_start]
    goals_html = html[goals_start:details_start]
    details_html = html[details_start:template_start]

    assert 'Classificação' in html
    assert 'Planejamento e Classificação' not in html
    assert 'Objetivos, resultados e indicadores' in html

    assert 'id="project_sei_process"' not in planning_html
    assert 'id="project_abep_indicator_input"' not in planning_html

    assert 'Indicadores EEGD' in goals_html
    assert 'Objetivo EEGD' in goals_html
    assert 'Resultado Esperado EEGD' in goals_html
    assert 'Indicadores ABEP' in goals_html
    assert 'id="project_abep_indicator_input"' in goals_html

    assert 'label-icon"></i>\n                                                        Objetivo\n' not in goals_html
    assert 'label-icon"></i>\n                                                        Resultado Esperado\n' not in goals_html

    assert 'Processo SEI-RJ' in details_html
    assert 'id="project_sei_process"' in details_html
