"""Controle exclusivo de `is_admin` pelo administrador principal (HTTP).

Cobre os 4 endpoints de escrita de ``/api/admin/usuarios*`` sob a política de
``services/admin_grant_policy.py``: só o super admin concede/remove `is_admin`,
só ele edita/exclui contas de administrador, e a conta principal nunca é
despromovida nem excluída. Toda negação de AUTORIZAÇÃO sai como
``403 forbidden``; os guards de negócio pré-existentes (último admin,
auto-exclusão) continuam ``422 validation``.

Fixtures: ``client_admin`` é o super admin do seed; ``client_admin_comum`` é um
administrador SEM o poder de concessão.
"""

from __future__ import annotations

from typing import Any

from models import User, db


def _ok(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "error" not in payload
    return payload["data"]


def _forbidden(response: Any) -> str:
    """Valida o envelope de negação de autorização e devolve a mensagem PT."""
    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False
    assert "data" not in payload
    assert payload["error"]["code"] == "forbidden"
    mensagem = payload["error"]["message"]
    assert isinstance(mensagem, str) and mensagem.strip()
    return mensagem


def _criar_admin(app, username: str) -> int:
    """Cria um administrador comum extra e devolve o id."""
    with app.app_context():
        user = User(
            username=username,
            name=username.replace("_", " ").title(),
            password_hash="x",
            is_admin=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _flags(app, user_id: int) -> tuple[bool, bool]:
    """``(is_admin, is_super_admin)`` persistidos do usuário."""
    with app.app_context():
        user = db.session.get(User, user_id)
        return bool(user.is_admin), bool(user.is_super_admin)


def _campo(app, user_id: int, campo: str) -> Any:
    with app.app_context():
        return getattr(db.session.get(User, user_id), campo)


def _existe(app, username: str) -> bool:
    with app.app_context():
        return User.query.filter_by(username=username).first() is not None


def _id_por_username(app, username: str) -> int:
    with app.app_context():
        return User.query.filter_by(username=username).first().id


# ---------------------------------------------------------------------------
# POST /api/admin/usuarios (criar)
# ---------------------------------------------------------------------------


def test_super_admin_cria_administrador(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": "novo_adm",
            "name": "Novo Adm",
            "password": "senhaForte123",
            "is_admin": True,
        },
    )

    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["usuario"]["is_admin"] is True
    assert data["usuario"]["is_super_admin"] is False
    assert _flags(app, _id_por_username(app, "novo_adm")) == (True, False)


def test_admin_comum_nao_cria_administrador(app, client_admin_comum, seed_data):
    """Nada de rebaixamento silencioso: erro explícito e usuário não nasce."""
    response = client_admin_comum.post(
        "/api/admin/usuarios",
        json={
            "username": "adm_proibido",
            "name": "Adm Proibido",
            "password": "senhaForte123",
            "is_admin": True,
        },
    )

    assert "administrador principal" in _forbidden(response)
    assert _existe(app, "adm_proibido") is False


def test_admin_comum_cria_usuario_sem_a_chave_is_admin(app, client_admin_comum):
    response = client_admin_comum.post(
        "/api/admin/usuarios",
        json={
            "username": "comum_sem_chave",
            "name": "Comum Sem Chave",
            "password": "senhaForte123",
        },
    )

    assert response.status_code == 200
    assert _ok(response.get_json())["usuario"]["is_admin"] is False


def test_admin_comum_cria_usuario_com_is_admin_false(app, client_admin_comum):
    response = client_admin_comum.post(
        "/api/admin/usuarios",
        json={
            "username": "comum_false",
            "name": "Comum False",
            "password": "senhaForte123",
            "is_admin": False,
        },
    )

    assert response.status_code == 200
    assert _ok(response.get_json())["usuario"]["is_admin"] is False


def test_payload_com_is_super_admin_e_ignorado_na_criacao(app, client_admin):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": "tentativa_super",
            "name": "Tentativa Super",
            "password": "senhaForte123",
            "is_admin": True,
            "is_super_admin": True,
        },
    )

    assert response.status_code == 200
    assert _ok(response.get_json())["usuario"]["is_super_admin"] is False
    assert _flags(app, _id_por_username(app, "tentativa_super")) == (True, False)


def test_autorizacao_vem_antes_da_validacao_na_criacao(app, client_admin_comum):
    """Payload inválido + `is_admin` proibido => 403 (não 422)."""
    response = client_admin_comum.post(
        "/api/admin/usuarios",
        json={"username": "sem_senha", "name": "Sem Senha", "is_admin": True},
    )

    _forbidden(response)
    assert _existe(app, "sem_senha") is False


# ---------------------------------------------------------------------------
# PUT /api/admin/usuarios/<id> (editar)
# ---------------------------------------------------------------------------


def test_admin_comum_nao_promove_usuario(app, client_admin_comum, seed_data):
    alvo = seed_data["editable_user_id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{alvo}",
        json={"name": "Usuario Editavel", "is_admin": True},
    )

    _forbidden(response)
    assert _flags(app, alvo) == (False, False)


def test_admin_comum_nao_rebaixa_outro_admin(app, client_admin_comum, seed_data):
    alvo = _criar_admin(app, "adm_alvo")
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{alvo}",
        json={"name": "Adm Alvo", "is_admin": False},
    )

    _forbidden(response)
    assert _flags(app, alvo) == (True, False)


def test_admin_comum_nao_rebaixa_o_super_admin(app, client_admin_comum, seed_data):
    alvo = seed_data["admin_id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{alvo}",
        json={"name": "Administrador", "is_admin": False},
    )

    _forbidden(response)
    assert _flags(app, alvo) == (True, True)


def test_admin_comum_nao_edita_nome_de_outro_admin(app, client_admin_comum, seed_data):
    alvo = _criar_admin(app, "adm_nome")
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{alvo}", json={"name": "Nome Trocado"}
    )

    _forbidden(response)
    assert _campo(app, alvo, "name") == "Adm Nome"


def test_admin_comum_edita_usuario_nao_admin(app, client_admin_comum, seed_data):
    alvo = seed_data["editable_user_id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{alvo}", json={"name": "Editado Por Admin Comum"}
    )

    assert response.status_code == 200
    assert _flags(app, alvo) == (False, False)
    assert _campo(app, alvo, "name") == "Editado Por Admin Comum"


def test_put_sem_is_admin_nao_rebaixa_o_proprio_ator(
    app, client_admin_comum, admin_comum
):
    """Ambiguidade resolvida: chave ausente MANTÉM a flag (antes rebaixava)."""
    ator = admin_comum["id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{ator}", json={"name": "Adm Secundario"}
    )

    assert response.status_code == 200
    assert _flags(app, ator) == (True, False)


def test_admin_comum_nao_se_auto_rebaixa(app, client_admin_comum, admin_comum):
    ator = admin_comum["id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{ator}",
        json={"name": "Adm Secundario", "is_admin": False},
    )

    _forbidden(response)
    assert _flags(app, ator) == (True, False)


def test_is_admin_igual_ao_atual_nao_gera_403(app, client_admin_comum, seed_data):
    alvo = seed_data["editable_user_id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{alvo}",
        json={"name": "Usuario Editavel", "is_admin": False},
    )

    assert response.status_code == 200
    assert _flags(app, alvo) == (False, False)


def test_is_admin_null_e_tratado_como_ausente(app, client_admin_comum, admin_comum):
    ator = admin_comum["id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{ator}",
        json={"name": "Adm Secundario", "is_admin": None},
    )

    assert response.status_code == 200
    assert _flags(app, ator) == (True, False)


def test_form_sem_campo_is_admin_mantem_o_valor_atual(
    app, client_admin_comum, admin_comum
):
    """Checkbox desmarcado (campo ausente no form) não rebaixa mais ninguém."""
    ator = admin_comum["id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{ator}", data={"name": "Adm Secundario"}
    )

    assert response.status_code == 200
    assert _flags(app, ator) == (True, False)


def test_super_admin_promove_usuario(app, client_admin, seed_data):
    alvo = seed_data["editable_user_id"]
    response = client_admin.put(
        f"/api/admin/usuarios/{alvo}",
        json={"name": "Usuario Editavel", "is_admin": True},
    )

    assert response.status_code == 200
    assert _ok(response.get_json())["usuario"]["is_admin"] is True
    assert _flags(app, alvo) == (True, False)


def test_super_admin_rebaixa_admin_comum(app, client_admin, admin_comum):
    response = client_admin.put(
        f"/api/admin/usuarios/{admin_comum['id']}",
        json={"name": "Adm Secundario", "is_admin": False},
    )

    assert response.status_code == 200
    assert _flags(app, admin_comum["id"]) == (False, False)


def test_super_admin_nao_se_auto_rebaixa(app, client_admin, seed_data, admin_comum):
    alvo = seed_data["admin_id"]
    response = client_admin.put(
        f"/api/admin/usuarios/{alvo}",
        json={"name": "Administrador", "is_admin": False},
    )

    mensagem = _forbidden(response)
    assert "administrador principal" in mensagem
    assert _flags(app, alvo) == (True, True)


def test_super_admin_edita_a_si_mesmo_sem_is_admin(app, client_admin, seed_data):
    alvo = seed_data["admin_id"]
    response = client_admin.put(
        f"/api/admin/usuarios/{alvo}", json={"name": "Administrador Geral"}
    )

    assert response.status_code == 200
    assert _flags(app, alvo) == (True, True)
    assert _campo(app, alvo, "name") == "Administrador Geral"


def test_is_super_admin_no_payload_do_put_e_ignorado(app, client_admin, seed_data):
    alvo = seed_data["admin_id"]
    response = client_admin.put(
        f"/api/admin/usuarios/{alvo}",
        json={"name": "Administrador", "is_super_admin": False},
    )

    assert response.status_code == 200
    assert _flags(app, alvo) == (True, True)


def test_valor_lixo_em_is_admin_vira_403_e_nao_422(
    app, client_admin_comum, admin_comum
):
    """ "talvez" normaliza para False, difere do atual => negação (não validação)."""
    ator = admin_comum["id"]
    response = client_admin_comum.put(
        f"/api/admin/usuarios/{ator}",
        json={"name": "Adm Secundario", "is_admin": "talvez"},
    )

    _forbidden(response)
    assert _flags(app, ator) == (True, False)


# ---------------------------------------------------------------------------
# DELETE /api/admin/usuarios/<id>
# ---------------------------------------------------------------------------


def test_admin_comum_exclui_usuario_nao_admin(app, client_admin_comum, seed_data):
    alvo = seed_data["deletable_user_id"]
    response = client_admin_comum.delete(f"/api/admin/usuarios/{alvo}")

    assert response.status_code == 200
    assert _campo(app, alvo, "deleted_at") is not None


def test_admin_comum_nao_exclui_outro_admin(app, client_admin_comum, seed_data):
    alvo = _criar_admin(app, "adm_excluivel")
    response = client_admin_comum.delete(f"/api/admin/usuarios/{alvo}")

    _forbidden(response)
    assert _campo(app, alvo, "deleted_at") is None


def test_admin_comum_nao_exclui_o_super_admin(app, client_admin_comum, seed_data):
    alvo = seed_data["admin_id"]
    response = client_admin_comum.delete(f"/api/admin/usuarios/{alvo}")

    _forbidden(response)
    assert _campo(app, alvo, "deleted_at") is None


def test_super_admin_exclui_admin_comum(app, client_admin, admin_comum):
    response = client_admin.delete(f"/api/admin/usuarios/{admin_comum['id']}")

    assert response.status_code == 200
    assert _campo(app, admin_comum["id"], "deleted_at") is not None


def test_super_admin_auto_exclusao_continua_422(app, client_admin, seed_data):
    """Guard de "própria conta" (pré-existente) vem antes da política: 422."""
    response = client_admin.delete(f"/api/admin/usuarios/{seed_data['admin_id']}")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"
    assert _campo(app, seed_data["admin_id"], "deleted_at") is None


def test_admin_comum_auto_exclusao_continua_422(app, client_admin_comum, admin_comum):
    ator = admin_comum["id"]
    response = client_admin_comum.delete(f"/api/admin/usuarios/{ator}")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"
    assert _campo(app, ator, "deleted_at") is None


# ---------------------------------------------------------------------------
# POST /api/admin/usuarios/<id>/remover-cpf
# ---------------------------------------------------------------------------


def test_admin_comum_nao_remove_cpf_de_outro_admin(app, client_admin_comum, seed_data):
    alvo = _criar_admin(app, "adm_com_cpf")
    with app.app_context():
        user = db.session.get(User, alvo)
        user.cpf_govbr = "12345678909"
        db.session.commit()

    response = client_admin_comum.post(f"/api/admin/usuarios/{alvo}/remover-cpf")

    _forbidden(response)
    assert _campo(app, alvo, "cpf_govbr") == "12345678909"


def test_admin_comum_remove_cpf_de_nao_admin(app, client_admin_comum, seed_data):
    alvo = seed_data["editable_user_id"]
    response = client_admin_comum.post(f"/api/admin/usuarios/{alvo}/remover-cpf")

    assert response.status_code == 200
    assert _campo(app, alvo, "cpf_govbr") is None


def test_super_admin_remove_cpf_de_admin_comum(app, client_admin, admin_comum):
    response = client_admin.post(f"/api/admin/usuarios/{admin_comum['id']}/remover-cpf")

    assert response.status_code == 200
    assert _campo(app, admin_comum["id"], "cpf_govbr") is None


# ---------------------------------------------------------------------------
# Leitura e serialização
# ---------------------------------------------------------------------------


def test_leitura_de_admin_continua_livre_para_admin_comum(
    app, client_admin_comum, seed_data
):
    """A política bloqueia ESCRITA; o detalhe segue legível (a SPA é quem esconde)."""
    response = client_admin_comum.get(f"/api/admin/usuarios/{seed_data['admin_id']}")

    assert response.status_code == 200
    assert _ok(response.get_json())["usuario"]["is_super_admin"] is True


def test_listagem_marca_apenas_o_super_admin(app, client_admin, seed_data, admin_comum):
    data = _ok(client_admin.get("/api/admin/usuarios").get_json())

    marcados = {u["id"] for u in data["usuarios"] if u["is_super_admin"]}
    assert marcados == {seed_data["admin_id"]}
    assert all("is_super_admin" in u for u in data["usuarios"])
    assert admin_comum["id"] in {u["id"] for u in data["usuarios"]}


def test_api_me_expoe_is_super_admin(client_admin, client_admin_comum, client_user):
    assert _ok(client_admin.get("/api/me").get_json())["is_super_admin"] is True
    assert _ok(client_admin_comum.get("/api/me").get_json())["is_super_admin"] is False
    assert _ok(client_user.get("/api/me").get_json())["is_super_admin"] is False


def test_payloads_novos_nao_vazam_segredos(client_admin, seed_data, admin_comum):
    lista = _ok(client_admin.get("/api/admin/usuarios").get_json())["usuarios"]
    detalhe = _ok(
        client_admin.get(f"/api/admin/usuarios/{seed_data['admin_id']}").get_json()
    )["usuario"]

    for usuario in [*lista, detalhe]:
        assert "password_hash" not in usuario
        assert "govbr_sub" not in usuario
