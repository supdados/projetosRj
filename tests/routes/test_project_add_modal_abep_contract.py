def test_project_add_modal_uses_abep_search_input(client_user):
    response = client_user.get('/projects')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="project_abep_indicator_search"' not in html
    assert 'id="project_abep_indicator_group"' not in html
    assert 'id="project_abep_indicator_input"' in html
    assert 'id="project_abep_indicator"' in html
    assert 'id="projectAbepIndicatorDropdown"' in html
