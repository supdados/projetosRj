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


def test_admin_can_create_user_with_valid_cpf_govbr(app, client_admin):
    response = client_admin.post(
        '/admin/users/add',
        data={
            'username': 'usuario_com_cpf',
            'name': 'Usuario CPF',
            'password': 'senhaNova123',
            'orgao': 'Orgao Novo',
            'areas_responsavel': ['Auditoria'],
            'cpf_govbr': '123.456.789-01',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/admin/users' in response.headers['Location']

    with app.app_context():
        user = User.query.filter_by(username='usuario_com_cpf').first()
        assert user is not None
        assert user.cpf_govbr == '12345678901'
        assert user.govbr_sub is None


def test_admin_user_create_rejects_invalid_cpf_govbr(app, client_admin):
    response = client_admin.post(
        '/admin/users/add',
        data={
            'username': 'usuario_cpf_invalido',
            'name': 'Usuario CPF Invalido',
            'password': 'senhaNova123',
            'orgao': 'Orgao Novo',
            'areas_responsavel': ['Auditoria'],
            'cpf_govbr': '12345',
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'CPF gov.br inválido' in html

    with app.app_context():
        assert User.query.filter_by(username='usuario_cpf_invalido').first() is None


def test_admin_user_create_rejects_duplicate_cpf_govbr(app, client_admin):
    with app.app_context():
        existing = User(
            username='usuario_cpf_existente',
            name='Usuario CPF Existente',
            orgao='Orgao Teste',
            is_admin=False,
            cpf_govbr='12345678901',
        )
        existing.set_password('senha123')
        db.session.add(existing)
        db.session.commit()

    response = client_admin.post(
        '/admin/users/add',
        data={
            'username': 'usuario_cpf_duplicado',
            'name': 'Usuario CPF Duplicado',
            'password': 'senhaNova123',
            'orgao': 'Orgao Novo',
            'areas_responsavel': ['Auditoria'],
            'cpf_govbr': '123.456.789-01',
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Já existe um usuário vinculado a este CPF gov.br.' in html

    with app.app_context():
        assert User.query.filter_by(username='usuario_cpf_duplicado').first() is None


def test_admin_edit_user_hides_cpf_and_sub_when_govbr_is_linked(app, client_admin, seed_data):
    with app.app_context():
        user = db.session.get(User, seed_data['editable_user_id'])
        user.cpf_govbr = '12345678901'
        user.govbr_sub = 'govbr-sub-editavel'
        db.session.commit()

    response = client_admin.get(f"/admin/users/edit/{seed_data['editable_user_id']}", follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Vinculado por gov.br' in page
    assert 'name="cpf_govbr"' not in page
    assert 'id="govbr_sub"' not in page


def test_admin_edit_linked_user_preserves_cpf_and_sub_when_fields_are_hidden(app, client_admin, seed_data):
    with app.app_context():
        user = db.session.get(User, seed_data['editable_user_id'])
        user.cpf_govbr = '12345678901'
        user.govbr_sub = 'govbr-sub-preserve'
        db.session.commit()

    response = client_admin.post(
        f"/admin/users/edit/{seed_data['editable_user_id']}",
        data={
            'name': 'Usuario Editado Sem Mexer Vínculo GovBR',
            'orgao': 'Orgao Atualizado',
            'areas_responsavel': ['Auditoria'],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/admin/users' in response.headers['Location']

    with app.app_context():
        user = db.session.get(User, seed_data['editable_user_id'])
        assert user is not None
        assert user.cpf_govbr == '12345678901'
        assert user.govbr_sub == 'govbr-sub-preserve'


def test_admin_own_profile_hides_cpf_and_sub_when_govbr_is_linked(app, client_admin, seed_data):
    with app.app_context():
        admin = db.session.get(User, seed_data['admin_id'])
        admin.cpf_govbr = '98765432100'
        admin.govbr_sub = 'govbr-sub-admin'
        db.session.commit()

    response = client_admin.get(f"/admin/users/edit/{seed_data['admin_id']}", follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Vinculado por gov.br' in page
    assert 'name="cpf_govbr"' not in page
    assert 'id="govbr_sub"' not in page


def test_admin_edit_user_does_not_render_sub_field_when_unlinked(client_admin, seed_data):
    response = client_admin.get(f"/admin/users/edit/{seed_data['editable_user_id']}", follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Identificador gov.br (sub)' not in page
    assert 'id="govbr_sub"' not in page
