"""Fluxos de login local, lockout, rate limit e logout.

Os testes do antigo formulário Jinja de /profile/change-password (troca de
senha + edição de nome/CPF gov.br) morreram com o corte da tela: a troca de
senha vive em POST /api/conta/senha (tests/routes/test_api_account_password.py)
e a edição de nome/vínculo gov.br ficou restrita ao admin (/api/admin/usuarios).
"""

from extensions import limiter
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


def test_login_lockout_blocks_correct_password_without_enumerating(
    app, client, seed_data
):
    """Durante o lockout o login é negado mesmo com a senha correta (CWE-307),
    e a resposta é idêntica à de usuário inexistente (sem enumeração)."""
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

    # Isola o lockout do rate-limit por conta (5/min): o loop esgotou o balde,
    # então zera o limiter para as asserções a seguir testarem só o lockout.
    limiter.reset()

    # Senha CORRETA é negada durante o bloqueio, com a mensagem genérica.
    locked_response = client.post(
        "/login?next=/projects",
        data={
            "username": seed_data["user_username"],
            "password": seed_data["user_password"],
        },
        follow_redirects=False,
    )
    locked_html = locked_response.get_data(as_text=True)
    assert locked_response.status_code == 200
    assert "Credenciais inválidas. Tente novamente." in locked_html
    assert "Conta temporariamente bloqueada" not in locked_html
    with client.session_transaction() as session:
        assert "user_id" not in session

    # Usuário inexistente: resposta idêntica (sem revelar quais contas existem).
    missing_response = client.post(
        "/login",
        data={"username": "usuario-inexistente", "password": "senha-invalida"},
        follow_redirects=False,
    )
    missing_html = missing_response.get_data(as_text=True)
    assert missing_response.status_code == 200
    assert "Credenciais inválidas. Tente novamente." in missing_html
    assert "Conta temporariamente bloqueada" not in missing_html

    # Expirado o bloqueio, a senha correta volta a autenticar (lockout é temporário).
    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.lockout_until = None
        db.session.commit()

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


def test_login_rate_limit_is_per_account_not_neighbor(client, seed_data):
    """Rate-limit por (IP+username): barra brute-force contra UMA conta a partir
    de um IP, sem afetar outra conta do mesmo IP (sem DoS do vizinho)."""
    limiter.reset()
    target = seed_data["user_username"]

    for _ in range(5):
        response = client.post(
            "/login",
            data={"username": target, "password": "senha-invalida"},
            follow_redirects=False,
        )
        assert response.status_code == 200

    # 6ª tentativa no MESMO usuário/IP é barrada pelo limite por conta (5/min).
    blocked = client.post(
        "/login",
        data={"username": target, "password": "senha-invalida"},
        follow_redirects=False,
    )
    assert blocked.status_code == 429

    # Outra conta no MESMO IP continua atendida — a chave é por conta.
    neighbor = client.post(
        "/login",
        data={"username": "outra-conta", "password": "senha-invalida"},
        follow_redirects=False,
    )
    assert neighbor.status_code == 200


def test_logout_clears_session_and_redirects_to_login(client_user):
    response = client_user.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    with client_user.session_transaction() as session:
        assert "user_id" not in session
