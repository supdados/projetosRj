from models import User, db


def test_admin_can_create_user_with_multiple_areas_and_password_hash(app, client_admin):
    response = client_admin.post(
        '/admin/users/add',
        data={
            'username': 'novo_multi_area',
            'name': 'Novo Multi Area',
            'password': 'senhaNova123',
            'orgao': 'Orgao Novo',
            'areas_responsavel': ['Auditoria', 'VPE'],
            'is_admin': 'on',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/admin/users' in response.headers['Location']

    with app.app_context():
        user = User.query.filter_by(username='novo_multi_area').first()
        assert user is not None
        assert user.name == 'Novo Multi Area'
        assert user.orgao == 'Orgao Novo'
        assert user.is_admin is True
        assert sorted(user.get_areas()) == ['Auditoria', 'VPE']
        assert user.password_hash != 'senhaNova123'
        assert user.check_password('senhaNova123') is True


def test_admin_user_create_rejects_invalid_area(app, client_admin):
    response = client_admin.post(
        '/admin/users/add',
        data={
            'username': 'usuario_area_invalida',
            'name': 'Usuario Area Invalida',
            'password': 'senhaNova123',
            'orgao': 'Orgao Novo',
            'areas_responsavel': ['Area Inexistente'],
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Área(s) inválida(s): Area Inexistente.' in html

    with app.app_context():
        assert User.query.filter_by(username='usuario_area_invalida').first() is None


def test_admin_can_edit_user_areas_password_and_profile(app, client_admin, seed_data):
    response = client_admin.post(
        f"/admin/users/edit/{seed_data['editable_user_id']}",
        data={
            'name': 'Usuario Editado com Permissoes',
            'orgao': 'Orgao Atualizado',
            'areas_responsavel': ['Auditoria', 'VPE'],
            'is_admin': 'on',
            'password': 'senhaAtualizada123',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/admin/users' in response.headers['Location']

    with app.app_context():
        user = db.session.get(User, seed_data['editable_user_id'])
        assert user is not None
        assert user.name == 'Usuario Editado com Permissoes'
        assert user.orgao == 'Orgao Atualizado'
        assert user.is_admin is True
        assert sorted(user.get_areas()) == ['Auditoria', 'VPE']
        assert user.check_password('senhaAtualizada123') is True


def test_admin_edit_blocks_demoting_the_only_admin(app, client_admin, seed_data):
    response = client_admin.post(
        f"/admin/users/edit/{seed_data['admin_id']}",
        data={
            'name': 'Administrador',
            'orgao': 'Orgao Teste',
            'areas_responsavel': ['Auditoria'],
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert 'Não é possível remover o status de administrador do único administrador existente.' in response.get_data(as_text=True)

    with app.app_context():
        admin = db.session.get(User, seed_data['admin_id'])
        assert admin is not None
        assert admin.is_admin is True


def test_admin_cannot_delete_own_account(app, client_admin, seed_data):
    response = client_admin.post(
        f"/admin/users/delete/{seed_data['admin_id']}",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert 'Você não pode excluir sua própria conta de administrador.' in response.get_data(as_text=True)

    with app.app_context():
        admin = db.session.get(User, seed_data['admin_id'])
        assert admin is not None
