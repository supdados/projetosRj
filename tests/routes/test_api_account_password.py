"""Contrato do POST /api/conta/senha (troca de senha self-service da SPA).

Substitui o fluxo Jinja de /profile/change-password (agora KEEP-ENDPOINT:
redirect 302 -> /conta/ajustes). A senha atual NÃO é exigida (decisão de
produto: conta gov.br pode não ter senha local). Cobre o envelope canônico em
cada desfecho e a efetivação real do hash (a senha nova passa a autenticar).
"""

import pytest

from extensions import limiter
from models import User, db


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Isola o rate limit 5/min entre os testes (storage do limiter é global)."""
    limiter.reset()


def _post_senha(http_client, body):
    return http_client.post("/api/conta/senha", json=body)


def test_troca_senha_com_sucesso_atualiza_hash(app, client_user, seed_data):
    response = _post_senha(
        client_user,
        {"nova_senha": "novaSenha123", "confirmacao": "novaSenha123"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["data"] == {"changed": True}

    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user.check_password("novaSenha123") is True
        assert user.check_password(seed_data["user_password"]) is False


def test_senha_atual_nao_e_exigida(app, client_user, seed_data):
    """Sem `senha_atual` no body a troca vale: é a decisão de produto do fluxo."""
    response = _post_senha(
        client_user,
        {"nova_senha": "outraSenha456", "confirmacao": "outraSenha456"},
    )

    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        assert user.check_password("outraSenha456") is True


def test_confirmacao_divergente_responde_400(client_user, seed_data):
    response = _post_senha(
        client_user,
        {"nova_senha": "novaSenha123", "confirmacao": "outraSenha123"},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation"
    assert body["error"]["message"] == "A nova senha e a confirmação não correspondem."


def test_forca_insuficiente_responde_400(client_user, seed_data):
    response = _post_senha(
        client_user,
        {"nova_senha": "curta", "confirmacao": "curta"},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation"
    assert "no mínimo 8 caracteres" in body["error"]["message"]


def test_campo_faltando_responde_400(client_user, seed_data):
    response = _post_senha(client_user, {"nova_senha": "novaSenha123"})

    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation"
    assert body["error"]["message"] == "Preencha a nova senha e a confirmação."


def test_sem_sessao_responde_401(client):
    response = _post_senha(
        client,
        {"nova_senha": "novaSenha123", "confirmacao": "novaSenha123"},
    )

    assert response.status_code == 401
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "unauthenticated"


def test_change_password_legado_redireciona_para_conta_senha(client_user):
    response = client_user.get("/profile/change-password", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/conta/ajustes")


def test_autoatendimento_nao_altera_nome_nem_cpf_govbr(app, client_user, seed_data):
    """O endpoint de senha ignora campos extras: nome/CPF têm endpoints próprios.

    Nome muda só via POST /api/conta/nome e o vínculo gov.br só via
    /api/conta/govbr* — payload extra aqui não pode ter efeito colateral.
    `senha_atual` entra na mesma vala: é ignorada desde que a régua deixou de
    pedi-la.
    """
    with app.app_context():
        antes = db.session.get(User, seed_data["user_id"])
        nome_antes, cpf_antes = antes.name, antes.cpf_govbr

    response = _post_senha(
        client_user,
        {
            "senha_atual": "irrelevante",
            "nova_senha": "novaSenha123",
            "confirmacao": "novaSenha123",
            "name": "Nome Invasor",
            "cpf_govbr": "12345678901",
        },
    )

    assert response.status_code == 200
    with app.app_context():
        depois = db.session.get(User, seed_data["user_id"])
        assert depois.name == nome_antes
        assert depois.cpf_govbr == cpf_antes
        assert depois.check_password("novaSenha123") is True
