from models import OrgaoUnidade, User, UserOrgao, db


def _login(client, user_id):
    with client.session_transaction() as session:
        session['user_id'] = user_id


def test_admin_create_user_persists_user_orgao_and_mirrors_user_area(app, seed_data):
    client = app.test_client()
    _login(client, seed_data['admin_id'])

    response = client.post(
        '/admin/users/add',
        data={
            'username': 'multi_orgao',
            'name': 'Multi Orgao',
            'password': 'senhaAaa123',
            'orgao': 'Livre',
            'orgaos_responsavel': [
                str(seed_data['auditoria_orgao_id']),
                str(seed_data['vpe_orgao_id']),
            ],
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        user = User.query.filter_by(username='multi_orgao').first()
        assert user is not None
        linked_ids = sorted(uo.orgao_id for uo in user.orgaos)
        assert linked_ids == sorted([
            seed_data['auditoria_orgao_id'], seed_data['vpe_orgao_id'],
        ])
        assert sorted(user.get_areas()) == ['Auditoria', 'VPE']


def test_admin_edit_user_swaps_orgaos(app, seed_data):
    client = app.test_client()
    _login(client, seed_data['admin_id'])

    with app.app_context():
        user = db.session.get(User, seed_data['editable_user_id'])
        initial_orgao_ids = [uo.orgao_id for uo in user.orgaos]
        assert initial_orgao_ids == [seed_data['auditoria_orgao_id']]

    response = client.post(
        f"/admin/users/edit/{seed_data['editable_user_id']}",
        data={
            'name': 'Usuario Editavel',
            'orgao': 'Livre',
            'orgaos_responsavel': [str(seed_data['vpd_orgao_id'])],
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        user = db.session.get(User, seed_data['editable_user_id'])
        linked_ids = [uo.orgao_id for uo in user.orgaos]
        assert linked_ids == [seed_data['vpd_orgao_id']]
        assert user.get_areas() == ['VPD']


def test_admin_edit_user_rejects_invalid_orgao_id(app, seed_data):
    client = app.test_client()
    _login(client, seed_data['admin_id'])

    response = client.post(
        f"/admin/users/edit/{seed_data['editable_user_id']}",
        data={
            'name': 'Usuario Editavel',
            'orgao': 'Livre',
            'orgaos_responsavel': ['9999999'],
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert 'Órgão(s) inválido(s):' in response.get_data(as_text=True)

    with app.app_context():
        user = db.session.get(User, seed_data['editable_user_id'])
        assert [uo.orgao_id for uo in user.orgaos] == [seed_data['auditoria_orgao_id']]
