from models import User, db
from tests._orgao_helpers import link_user_to_orgao


def test_projetos_pendentes_template_uses_short_done_toast(client_user):
    response = client_user.get('/projetos_pendentes')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "showToast('Etapa concluída', 'info');" in html
    assert 'removida da triagem' not in html


def test_projetos_pendentes_shows_orgao_filter_for_non_admin_with_multiple_orgaos(app, client, seed_data):
    with app.app_context():
        user = User(
            username='user_multi_orgao_pending',
            name='Usuario Multi Orgao Pending',
            orgao='Orgao Multi',
            is_admin=False,
        )
        user.set_password('senha123')
        db.session.add(user)
        db.session.flush()
        link_user_to_orgao(user.id, 'Auditoria')
        link_user_to_orgao(user.id, 'VPD')
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as session:
        session['user_id'] = user_id

    response = client.get('/projetos_pendentes')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="orgaoFilter"' in html
    assert 'Projeto Auditoria' in html
    assert 'Projeto VPD' in html

    vpd_orgao_id = seed_data['vpd_orgao_id']
    response = client.get('/projetos_pendentes', query_string={'orgao': str(vpd_orgao_id)})
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="orgaoFilter"' in html
    assert 'Projeto VPD' in html
    assert 'Projeto Auditoria' not in html
    assert f'<option value="{vpd_orgao_id}" selected' in html


def test_projetos_pendentes_redirects_when_non_admin_forces_foreign_area(client_user, seed_data):
    response = client_user.get(
        '/projetos_pendentes',
        query_string={'orgao': str(seed_data['vpe_orgao_id']), 'periodo': '7dias'},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/projetos_pendentes?periodo=7dias')
