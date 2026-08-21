"""Contrato dos endpoints de Ajustes da conta (GET/POST /api/conta*).

Cobre o autoatendimento da tela SPA /conta/ajustes: identidade exibida no card
lateral (nome, username e sigla do órgão-âncora), nome de exibição, vínculo
gov.br (estados nenhum/cpf_pendente/vinculado, com mascaramento de CPF) e a
regra de que o username nunca muda por aqui.
"""

import pytest

from extensions import limiter
from models import User, UserOrgao, db

CPF_VALIDO = "52998224725"
# `seed_data` vincula `user_auditoria` só a este órgão — é o primário esperado.
SIGLA_DO_USUARIO = "Auditoria"


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    limiter.reset()


def _get_user(app, seed_data):
    with app.app_context():
        return db.session.get(User, seed_data["user_id"])


def test_get_conta_sem_vinculo(client_user, seed_data):
    response = client_user.get("/api/conta")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["name"]
    assert data["username"]
    assert data["orgao_sigla"] == SIGLA_DO_USUARIO
    assert data["govbr"] == {"status": "nenhum", "cpf_mascarado": None}


def test_get_conta_sem_orgao_devolve_sigla_nula(app, client_user, seed_data):
    with app.app_context():
        UserOrgao.query.filter_by(user_id=seed_data["user_id"]).delete()
        db.session.commit()

    data = client_user.get("/api/conta").get_json()["data"]
    assert data["orgao_sigla"] is None


def test_get_conta_cpf_pendente_mascara_3_digitos(app, client_user, seed_data):
    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = CPF_VALIDO
        db.session.commit()

    data = client_user.get("/api/conta").get_json()["data"]
    assert data["orgao_sigla"] == SIGLA_DO_USUARIO
    assert data["govbr"]["status"] == "cpf_pendente"
    assert data["govbr"]["cpf_mascarado"] == "529********"
    assert CPF_VALIDO not in str(data)


def test_get_conta_vinculado_nao_expoe_nenhum_digito(app, client_user, seed_data):
    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = CPF_VALIDO
        user.govbr_sub = "sub-govbr-123"
        db.session.commit()

    data = client_user.get("/api/conta").get_json()["data"]
    assert data["orgao_sigla"] == SIGLA_DO_USUARIO
    assert data["govbr"] == {"status": "vinculado", "cpf_mascarado": None}
    assert "529" not in str(data["govbr"])


def test_trocar_nome_atualiza_sem_tocar_username(app, client_user, seed_data):
    antes = _get_user(app, seed_data)
    username_antes = antes.username

    response = client_user.post(
        "/api/conta/nome", json={"name": "  Nome Novo  ", "username": "invasor"}
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {"name": "Nome Novo"}
    depois = _get_user(app, seed_data)
    assert depois.name == "Nome Novo"
    assert depois.username == username_antes


def test_trocar_nome_vazio_responde_400(client_user, seed_data):
    response = client_user.post("/api/conta/nome", json={"name": "   "})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation"


def test_vincular_cpf_normaliza_pontuacao(app, client_user, seed_data):
    response = client_user.post("/api/conta/govbr", json={"cpf": "529.982.247-25"})

    assert response.status_code == 200
    govbr = response.get_json()["data"]["govbr"]
    assert govbr == {"status": "cpf_pendente", "cpf_mascarado": "529********"}
    assert _get_user(app, seed_data).cpf_govbr == CPF_VALIDO


def test_vincular_cpf_malformado_responde_400(client_user, seed_data):
    response = client_user.post("/api/conta/govbr", json={"cpf": "123"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation"


def test_vincular_com_vinculo_existente_responde_400(app, client_user, seed_data):
    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = CPF_VALIDO
        db.session.commit()

    response = client_user.post("/api/conta/govbr", json={"cpf": "11144477735"})

    assert response.status_code == 400
    assert _get_user(app, seed_data).cpf_govbr == CPF_VALIDO


def test_vincular_cpf_de_outra_conta_responde_400_generico(app, client_user, seed_data):
    with app.app_context():
        outro = User(username="outro.dono", name="Outro Dono")
        outro.set_password("senhaForte123")
        outro.cpf_govbr = CPF_VALIDO
        db.session.add(outro)
        db.session.commit()

    response = client_user.post("/api/conta/govbr", json={"cpf": CPF_VALIDO})

    assert response.status_code == 400
    mensagem = response.get_json()["error"]["message"]
    assert "outro" not in mensagem.lower()


def test_remover_vinculo_limpa_cpf_e_sub(app, client_user, seed_data):
    with app.app_context():
        user = db.session.get(User, seed_data["user_id"])
        user.cpf_govbr = CPF_VALIDO
        user.govbr_sub = "sub-govbr-123"
        db.session.commit()

    response = client_user.post("/api/conta/govbr/remover")

    assert response.status_code == 200
    assert response.get_json()["data"]["govbr"] == {
        "status": "nenhum",
        "cpf_mascarado": None,
    }
    depois = _get_user(app, seed_data)
    assert depois.cpf_govbr is None
    assert depois.govbr_sub is None


def test_remover_sem_vinculo_responde_400(client_user, seed_data):
    response = client_user.post("/api/conta/govbr/remover")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation"


def test_endpoints_de_conta_exigem_sessao(client):
    assert client.get("/api/conta").status_code == 401
    assert client.post("/api/conta/nome", json={"name": "x"}).status_code == 401
    assert client.post("/api/conta/govbr", json={"cpf": CPF_VALIDO}).status_code == 401
    assert client.post("/api/conta/govbr/remover").status_code == 401
