from models import User, UserArea, db


def test_projetos_pendentes_template_uses_short_done_toast(client_user):
    response = client_user.get('/projetos_pendentes')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "showToast('Etapa concluída', 'info');" in html
    assert 'removida da triagem' not in html


def test_projetos_pendentes_shows_area_filter_for_non_admin_with_multiple_areas(app, client, seed_data):
    with app.app_context():
        user = User(
            username='user_multi_area_pending',
            name='Usuario Multi Area Pending',
            orgao='Orgao Multi',
            is_admin=False,
        )
        user.set_password('senha123')
        db.session.add(user)
        db.session.flush()
        db.session.add_all(
            [
                UserArea(user_id=user.id, area='Auditoria'),
                UserArea(user_id=user.id, area='VPD'),
            ]
        )
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as session:
        session['user_id'] = user_id

    response = client.get('/projetos_pendentes')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="areaFilter"' in html
    assert '<option value="Auditoria"' in html
    assert '<option value="VPD"' in html
    assert 'Projeto Auditoria' in html
    assert 'Projeto VPD' in html

    response = client.get('/projetos_pendentes', query_string={'area': 'VPD'})
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="areaFilter"' in html
    assert 'Projeto VPD' in html
    assert 'Projeto Auditoria' not in html
    assert '<option value="VPD" selected' in html
