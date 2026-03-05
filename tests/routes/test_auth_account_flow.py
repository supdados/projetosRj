from models import User, db


def test_login_success_redirects_to_next_and_sets_session(client, seed_data):
    response = client.post(
        '/login?next=/projects',
        data={
            'username': seed_data['user_username'],
            'password': seed_data['user_password'],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/projects')

    with client.session_transaction() as session:
        assert session['user_id'] == seed_data['user_id']


def test_login_invalid_credentials_keeps_user_logged_out(client, seed_data):
    response = client.post(
        '/login',
        data={
            'username': seed_data['user_username'],
            'password': 'senha-invalida',
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert 'Credenciais inválidas. Tente novamente.' in response.get_data(as_text=True)

    with client.session_transaction() as session:
        assert 'user_id' not in session


def test_logout_clears_session_and_redirects_to_login(client_user):
    response = client_user.get('/logout', follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.headers['Location']

    with client_user.session_transaction() as session:
        assert 'user_id' not in session


def test_change_password_rejects_wrong_current_password(app, client_user, seed_data):
    response = client_user.post(
        '/profile/change-password',
        data={
            'current_password': 'senha-errada',
            'new_password': 'novaSenha123',
            'confirm_new_password': 'novaSenha123',
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert 'Senha atual incorreta.' in response.get_data(as_text=True)

    with app.app_context():
        user = db.session.get(User, seed_data['user_id'])
        assert user is not None
        assert user.check_password(seed_data['user_password']) is True
        assert user.check_password('novaSenha123') is False


def test_change_password_updates_hash_and_accepts_new_password(app, client_user, seed_data):
    response = client_user.post(
        '/profile/change-password',
        data={
            'current_password': seed_data['user_password'],
            'new_password': 'novaSenha123',
            'confirm_new_password': 'novaSenha123',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/dashboard' in response.headers['Location']

    with app.app_context():
        user = db.session.get(User, seed_data['user_id'])
        assert user is not None
        assert user.check_password(seed_data['user_password']) is False
        assert user.check_password('novaSenha123') is True


def test_manage_account_updates_name_and_cpf_without_changing_login(app, client_user, seed_data):
    response = client_user.post(
        '/profile/change-password',
        data={
            'name': 'Usuario Atualizado',
            'cpf_govbr': '123.456.789-01',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/dashboard' in response.headers['Location']

    with app.app_context():
        user = db.session.get(User, seed_data['user_id'])
        assert user is not None
        assert user.name == 'Usuario Atualizado'
        assert user.username == seed_data['user_username']
        assert user.cpf_govbr == '12345678901'


def test_manage_account_hides_cpf_and_sub_when_user_is_linked_to_govbr(app, client_user, seed_data):
    with app.app_context():
        user = db.session.get(User, seed_data['user_id'])
        user.cpf_govbr = '12345678901'
        user.govbr_sub = 'govbr-sub-123'
        db.session.commit()

    response = client_user.get('/profile/change-password', follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Vinculado por gov.br' in page
    assert 'name="cpf_govbr"' not in page
    assert 'id="govbr_sub"' not in page


def test_non_admin_menu_shows_manage_account_entry(client_user):
    response = client_user.get('/dashboard', follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Gerenciar Conta' in page
