def test_public_home_renders_portfolio_overview_for_anonymous_users(client):
    response = client.get('/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Visão pública do portfólio' in html
    assert 'Radar por área responsável' in html
    assert 'Status do portfólio' in html
    assert 'Prioridade operacional' in html
    assert 'href="/login"' in html
    assert 'data-skeleton-active="public"' in html
    assert 'id="appThemeToggle"' not in html


def test_public_home_uses_seeded_aggregations(client, seed_data):
    response = client.get('/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Projetos monitorados' in html
    assert '>3<' in html
    assert 'Portfólio vigente' in html
    assert '>3<' in html
    assert 'Projetos em atraso' in html
    assert '>2<' in html
    assert 'Tarefas abertas' in html
    assert '>3<' in html
    assert 'Auditoria' in html
    assert 'VPD' in html
