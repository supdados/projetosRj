from models import User, db


def test_login_success_redirects_to_next_and_sets_session(client, seed_data):
    response = client.post(
        "/login?next=/projects",
        data={
            "username": seed_data["user_username"],
            "password": seed_data["user_password"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/projects")

    with client.session_transaction() as session:
        assert session["user_id"] == seed_data["user_id"]


def test_login_invalid_credentials_keeps_user_logged_out(client, seed_data):
    response = client.post(
        "/login",
        data={
            "username": seed_data["user_username"],
            "password": "senha-invalida",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Credenciais inválidas. Tente novamente." in response.get_data(as_text=True)

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_login_lockout_does_not_block_owner_or_enumerate_users(app, client, seed_data):
    for _ in range(5):
        response = client.post(
            "/login",
            data={
                "username": seed_data["user_username"],
                "password": "senha-invalida",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Credenciais inválidas. Tente novamente." in response.get_data(
            as_text=True
        )

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user is not None
        assert user.lockout_until is not None

    locked_response = client.post(
        "/login",
        data={
            "username": seed_data["user_username"],
            "password": "outra-senha-invalida",
        },
        follow_redirects=False,
    )
    locked_html = locked_response.get_data(as_text=True)
    assert locked_response.status_code == 200
    assert "Credenciais inválidas. Tente novamente." in locked_html
    assert "Conta temporariamente bloqueada" not in locked_html

    missing_response = client.post(
        "/login",
        data={"username": "usuario-inexistente", "password": "senha-invalida"},
        follow_redirects=False,
    )
    missing_html = missing_response.get_data(as_text=True)
    assert missing_response.status_code == 200
    assert "Credenciais inválidas. Tente novamente." in missing_html
    assert "Conta temporariamente bloqueada" not in missing_html

    success_response = client.post(
        "/login?next=/projects",
        data={
            "username": seed_data["user_username"],
            "password": seed_data["user_password"],
        },
        follow_redirects=False,
    )
    assert success_response.status_code == 302
    assert success_response.headers["Location"].endswith("/projects")

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user.lockout_until is None
        assert user.failed_login_attempts == 0


def test_logout_clears_session_and_redirects_to_login(client_user):
    response = client_user.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    with client_user.session_transaction() as session:
        assert "user_id" not in session


def test_change_password_rejects_wrong_current_password(app, client_user, seed_data):
    response = client_user.post(
        "/profile/change-password",
        data={
            "current_password": "senha-errada",
            "new_password": "novaSenha123",
            "confirm_new_password": "novaSenha123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Senha atual incorreta." in response.get_data(as_text=True)

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user is not None
        assert user.check_password(seed_data["user_password"]) is True
        assert user.check_password("novaSenha123") is False


def test_change_password_updates_hash_and_accepts_new_password(
    app, client_user, seed_data
):
    response = client_user.post(
        "/profile/change-password",
        data={
            "current_password": seed_data["user_password"],
            "new_password": "novaSenha123",
            "confirm_new_password": "novaSenha123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user is not None
        assert user.check_password(seed_data["user_password"]) is False
        assert user.check_password("novaSenha123") is True


def test_manage_account_updates_name_without_changing_login_or_cpf(
    app, client_user, seed_data
):
    response = client_user.post(
        "/profile/change-password",
        data={
            "name": "Usuario Atualizado",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user is not None
        assert user.name == "Usuario Atualizado"
        assert user.username == seed_data["user_username"]
        assert user.cpf_govbr is None


def test_manage_account_rejects_self_service_cpf_change(app, client_user, seed_data):
    response = client_user.post(
        "/profile/change-password",
        data={
            "name": "Usuario Atualizado",
            "cpf_govbr": "123.456.789-01",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert (
        "Alteração de CPF gov.br por autoatendimento está desativada."
        in response.get_data(as_text=True)
    )

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user is not None
        assert user.name == "Usuario Auditoria"
        assert user.cpf_govbr is None


def test_manage_account_hides_cpf_and_sub_when_user_is_linked_to_govbr(
    app, client_user, seed_data
):
    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = "12345678901"
        user.govbr_sub = "govbr-sub-123"
        db.session.commit()

    response = client_user.get("/profile/change-password", follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Vinculado por gov.br" in page
    assert 'name="cpf_govbr"' not in page
    assert 'id="govbr_sub"' not in page


def test_non_admin_menu_shows_manage_account_entry(client_user):
    # O menu de conta vive no app-shell Jinja, renderizado nas páginas de auth
    # (/projects virou redirect SPA). Usamos /profile/change-password (autenticada).
    response = client_user.get("/profile/change-password", follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Gerenciar Conta" in page


def test_manage_account_does_not_render_sub_field_for_unlinked_user(client_user):
    response = client_user.get("/profile/change-password", follow_redirects=False)

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Para alterar o CPF gov.br, solicite ao administrador." in page
    assert 'name="cpf_govbr"' not in page
    assert "Identificador gov.br (sub)" not in page
    assert 'id="govbr_sub"' not in page
