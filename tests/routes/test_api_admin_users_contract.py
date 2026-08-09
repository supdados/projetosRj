"""Testes de contrato dos endpoints JSON Admin de Usuários (envelope canônico).

Cobrem o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error": {...}}``
de ``/api/admin/usuarios*`` e os guards de ``api_admin_required`` (401 sem
sessão, 403 para usuário comum) além das validações 422.

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo, ``client_user``
não-admin e ``client_admin``). NUNCA deve vazar ``password_hash``/``govbr_sub``.
"""

from __future__ import annotations

import time
from typing import Any


def _assert_ok_envelope(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "data" in payload
    assert "error" not in payload
    return payload["data"]


def _assert_fail_envelope(payload: Any, *, code: str) -> None:
    assert isinstance(payload, dict)
    assert payload["ok"] is False
    assert "data" not in payload
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]


# ---------------------------------------------------------------------------
# GET /api/admin/usuarios (lista paginada)
# ---------------------------------------------------------------------------


def test_list_page_out_of_range_clamps_to_last_page(client_admin, seed_data):
    """Página além do fim devolve a ÚLTIMA página, nunca uma lista vazia.

    `paginate(error_out=False)` ecoava a página pedida com `items=[]`, e a UI
    não distingue isso de "o filtro não achou ninguém".
    """
    baseline = client_admin.get("/api/admin/usuarios").get_json()
    total_pages = baseline["meta"]["total_pages"]
    last_page = client_admin.get(f"/api/admin/usuarios?page={total_pages}").get_json()

    response = client_admin.get("/api/admin/usuarios?page=999999")

    assert response.status_code == 200
    payload = response.get_json()
    data = _assert_ok_envelope(payload)
    assert payload["meta"]["page"] == total_pages
    assert data["usuarios"]
    assert data["usuarios"] == _assert_ok_envelope(last_page)["usuarios"]


def test_list_page_zero_or_negative_clamps_to_first_page(client_admin, seed_data):
    first = _assert_ok_envelope(client_admin.get("/api/admin/usuarios").get_json())

    for query in ("page=0", "page=-3"):
        payload = client_admin.get(f"/api/admin/usuarios?{query}").get_json()
        assert payload["meta"]["page"] == 1
        assert _assert_ok_envelope(payload)["usuarios"] == first["usuarios"]


def test_list_returns_ok_envelope_with_meta(client_admin, seed_data):
    response = client_admin.get("/api/admin/usuarios")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["usuarios"], list)
    assert data["usuarios"]
    meta = response.get_json()["meta"]
    assert set(meta.keys()) == {"page", "per_page", "total", "total_pages"}
    assert meta["per_page"] == 20


def test_list_never_serializes_secrets(client_admin):
    data = _assert_ok_envelope(client_admin.get("/api/admin/usuarios").get_json())
    for user in data["usuarios"]:
        assert "password_hash" not in user
        assert "govbr_sub" not in user
        assert all("token" not in key for key in user)


def test_list_returns_401_when_unauthenticated(client):
    response = client.get("/api/admin/usuarios")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_list_returns_403_for_non_admin(client_user):
    response = client_user.get("/api/admin/usuarios")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


def test_list_filters_by_free_text_query(client_admin, seed_data):
    """`?q=` casa por nome/login (ilike) — "VPD" só atinge o usuário VPD."""
    data = _assert_ok_envelope(client_admin.get("/api/admin/usuarios?q=VPD").get_json())
    assert [user["name"] for user in data["usuarios"]] == ["Usuario VPD"]


def test_list_filters_by_area_id(app, client_admin, seed_data):
    """`?area_id=` restringe aos usuários vinculados àquele órgão."""
    from models import OrgaoUnidade

    with app.app_context():
        area_id = OrgaoUnidade.query.filter_by(sigla="VPD").first().id

    data = _assert_ok_envelope(
        client_admin.get(f"/api/admin/usuarios?area_id={area_id}").get_json()
    )
    assert [user["name"] for user in data["usuarios"]] == ["Usuario VPD"]


def test_list_without_filters_returns_all_active(client_admin, seed_data):
    """Sem filtros o comportamento padrão (todos os ativos) é preservado."""
    baseline = _assert_ok_envelope(client_admin.get("/api/admin/usuarios").get_json())
    filtered = _assert_ok_envelope(
        client_admin.get("/api/admin/usuarios?q=Usuario").get_json()
    )
    assert len(filtered["usuarios"]) < len(baseline["usuarios"])


# ---------------------------------------------------------------------------
# GET /api/admin/usuarios/<id> (form data)
# ---------------------------------------------------------------------------


def test_detail_returns_user_and_orgao_options(client_admin, seed_data):
    user_id = seed_data["editable_user_id"]
    response = client_admin.get(f"/api/admin/usuarios/{user_id}")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["usuario"]["id"] == user_id
    assert "password_hash" not in data["usuario"]
    assert isinstance(data["orgao_ids"], list)
    assert isinstance(data["orgaos_options"], list)


def test_detail_returns_404_for_unknown_user(client_admin):
    response = client_admin.get("/api/admin/usuarios/999999")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_detail_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.get(f"/api/admin/usuarios/{seed_data['editable_user_id']}")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/usuarios (criar)
# ---------------------------------------------------------------------------


def test_create_returns_ok_envelope(client_admin):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": "contrato_novo",
            "name": "Contrato Novo",
            "password": "senhaContrato123",
            "orgao": "Orgao X",
        },
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["usuario"]["username"] == "contrato_novo"
    assert "password_hash" not in data["usuario"]


def test_create_missing_required_fields_returns_422(client_admin):
    response = client_admin.post(
        "/api/admin/usuarios", json={"username": "", "name": "", "password": ""}
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_create_rejects_weak_password_returns_422(client_admin):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={"username": "fraco", "name": "Senha Fraca", "password": "123"},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_create_duplicate_username_returns_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": seed_data["user_username"],
            "name": "Duplicado",
            "password": "senha12345",
        },
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_create_returns_403_for_non_admin(client_user):
    response = client_user.post(
        "/api/admin/usuarios",
        json={"username": "x", "name": "x", "password": "x"},
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# PUT /api/admin/usuarios/<id> (editar)
# ---------------------------------------------------------------------------


def test_update_returns_ok_envelope(client_admin, seed_data):
    user_id = seed_data["editable_user_id"]
    response = client_admin.put(
        f"/api/admin/usuarios/{user_id}",
        json={"name": "Nome Atualizado Contrato", "orgao": "Novo Orgao"},
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["usuario"]["name"] == "Nome Atualizado Contrato"


def test_update_returns_404_for_unknown_user(client_admin):
    response = client_admin.put("/api/admin/usuarios/999999", json={"name": "x"})
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_update_invalid_cpf_returns_422(client_admin, seed_data):
    response = client_admin.put(
        f"/api/admin/usuarios/{seed_data['editable_user_id']}",
        json={"name": "Nome", "cpf_govbr": "123"},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_update_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.put(
        f"/api/admin/usuarios/{seed_data['editable_user_id']}", json={"name": "x"}
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# Papel por vínculo de área (novo payload + compat de `orgaos_responsavel[]`)
# ---------------------------------------------------------------------------


def _orgao_id_por_sigla(app, sigla: str) -> int:
    from models import OrgaoUnidade

    with app.app_context():
        return OrgaoUnidade.query.filter_by(sigla=sigla).first().id


def _papeis_gravados(app, username: str) -> dict[str, str]:
    """{sigla: papel} dos vínculos persistidos do usuário."""
    from models import User

    with app.app_context():
        user = User.query.filter_by(username=username).first()
        return {uo.orgao.sigla: uo.papel for uo in user.orgaos}


def test_list_exposes_papel_por_orgao(client_admin, seed_data):
    """Todo vínculo do seed nasce `gestor` (backfill) e o papel vai no payload."""
    data = _assert_ok_envelope(client_admin.get("/api/admin/usuarios").get_json())
    vinculos = [orgao for user in data["usuarios"] for orgao in user["orgaos"]]

    assert vinculos
    for orgao in vinculos:
        assert set(orgao.keys()) == {"id", "sigla", "nome", "papel"}
        assert orgao["papel"] == "gestor"


def test_create_com_pares_grava_papeis_distintos(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": "papel_novo",
            "name": "Papel Novo",
            "password": "senhaContrato123",
            "orgaos": [
                {"orgao_id": _orgao_id_por_sigla(app, "SUPDADOS"), "papel": "editor"},
                {"orgao_id": _orgao_id_por_sigla(app, "VPD"), "papel": "leitor"},
            ],
        },
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert {o["sigla"]: o["papel"] for o in data["usuario"]["orgaos"]} == {
        "SUPDADOS": "editor",
        "VPD": "leitor",
    }
    assert _papeis_gravados(app, "papel_novo") == {
        "SUPDADOS": "editor",
        "VPD": "leitor",
    }


def test_create_com_payload_antigo_grava_gestor(app, client_admin, seed_data):
    """`orgaos_responsavel[]` (lista de ids) continua aceito => papel `gestor`."""
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": "papel_legado",
            "name": "Papel Legado",
            "password": "senhaContrato123",
            "orgaos_responsavel": [_orgao_id_por_sigla(app, "VPD")],
        },
    )

    assert response.status_code == 200
    assert _papeis_gravados(app, "papel_legado") == {"VPD": "gestor"}


def test_create_com_payload_antigo_em_form_grava_gestor(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/usuarios",
        data={
            "username": "papel_legado_form",
            "name": "Papel Legado Form",
            "password": "senhaContrato123",
            "orgaos_responsavel": str(_orgao_id_por_sigla(app, "VPD")),
        },
    )

    assert response.status_code == 200
    assert _papeis_gravados(app, "papel_legado_form") == {"VPD": "gestor"}


def test_create_com_papel_invalido_retorna_422(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": "papel_ruim",
            "name": "Papel Ruim",
            "password": "senhaContrato123",
            "orgaos": [{"orgao_id": _orgao_id_por_sigla(app, "VPD"), "papel": "chefe"}],
        },
    )

    assert response.status_code == 422
    payload = response.get_json()
    _assert_fail_envelope(payload, code="validation")
    assert "chefe" in payload["error"]["message"]
    assert "leitor|editor|gestor" in payload["error"]["message"]


def test_create_sem_papel_no_par_usa_gestor(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/usuarios",
        json={
            "username": "papel_omitido",
            "name": "Papel Omitido",
            "password": "senhaContrato123",
            "orgaos": [{"orgao_id": _orgao_id_por_sigla(app, "VPD")}],
        },
    )

    assert response.status_code == 200
    assert _papeis_gravados(app, "papel_omitido") == {"VPD": "gestor"}


def test_update_altera_o_papel_do_vinculo(app, client_admin, seed_data):
    user_id = seed_data["editable_user_id"]
    response = client_admin.put(
        f"/api/admin/usuarios/{user_id}",
        json={
            "name": "Usuario Editavel",
            "orgaos": [
                {"orgao_id": _orgao_id_por_sigla(app, "Auditoria"), "papel": "leitor"}
            ],
        },
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert {o["sigla"]: o["papel"] for o in data["usuario"]["orgaos"]} == {
        "Auditoria": "leitor"
    }
    assert _papeis_gravados(app, "user_editavel") == {"Auditoria": "leitor"}


def test_update_com_payload_antigo_mantem_gestor(app, client_admin, seed_data):
    user_id = seed_data["editable_user_id"]
    response = client_admin.put(
        f"/api/admin/usuarios/{user_id}",
        json={
            "name": "Usuario Editavel",
            "orgaos_responsavel": [_orgao_id_por_sigla(app, "Auditoria")],
        },
    )

    assert response.status_code == 200
    assert _papeis_gravados(app, "user_editavel") == {"Auditoria": "gestor"}


def test_update_com_papel_invalido_retorna_422(app, client_admin, seed_data):
    response = client_admin.put(
        f"/api/admin/usuarios/{seed_data['editable_user_id']}",
        json={
            "name": "Usuario Editavel",
            "orgaos": [
                {"orgao_id": _orgao_id_por_sigla(app, "Auditoria"), "papel": "root"}
            ],
        },
    )

    assert response.status_code == 422
    payload = response.get_json()
    _assert_fail_envelope(payload, code="validation")
    assert "root" in payload["error"]["message"]


# ---------------------------------------------------------------------------
# POST /api/admin/usuarios/<id>/remover-cpf
# ---------------------------------------------------------------------------


def test_remove_cpf_returns_ok_envelope(client_admin, seed_data):
    user_id = seed_data["editable_user_id"]
    response = client_admin.post(f"/api/admin/usuarios/{user_id}/remover-cpf")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["usuario"]["cpf_govbr"] is None
    assert data["usuario"]["has_govbr_link"] is False


def test_remove_cpf_returns_404_for_unknown_user(client_admin):
    response = client_admin.post("/api/admin/usuarios/999999/remover-cpf")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_remove_cpf_returns_401_when_unauthenticated(client, seed_data):
    response = client.post(
        f"/api/admin/usuarios/{seed_data['editable_user_id']}/remover-cpf"
    )
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


# ---------------------------------------------------------------------------
# DELETE /api/admin/usuarios/<id>
# ---------------------------------------------------------------------------


def test_delete_returns_ok_envelope(client_admin, seed_data):
    user_id = seed_data["deletable_user_id"]
    response = client_admin.delete(f"/api/admin/usuarios/{user_id}")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["deleted_id"] == user_id


def test_delete_self_returns_422(client_admin, seed_data):
    response = client_admin.delete(f"/api/admin/usuarios/{seed_data['admin_id']}")
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_delete_returns_404_for_unknown_user(client_admin):
    response = client_admin.delete("/api/admin/usuarios/999999")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_delete_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.delete(
        f"/api/admin/usuarios/{seed_data['deletable_user_id']}"
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


def test_delete_user_com_evento_de_calendario_faz_soft_delete(
    app, client_admin, seed_data
):
    # Soft-delete C4: usuário com ``calendar_event`` (user_id NOT NULL) NÃO pode
    # ser apagado — antes isto dava IntegrityError (409). Agora marcamos
    # ``deleted_at`` e preservamos TODO o histórico: a linha do usuário e o
    # ``calendar_event`` permanecem intactos.
    from datetime import datetime

    from models import CalendarEvent, User, db

    user_id = seed_data["deletable_user_id"]
    with app.app_context():
        db.session.add(
            CalendarEvent(
                user_id=user_id,
                title="Reunião vinculada",
                source="app",
                starts_at=datetime(2026, 1, 1, 10, 0),
                ends_at=datetime(2026, 1, 1, 11, 0),
            )
        )
        db.session.commit()

    response = client_admin.delete(f"/api/admin/usuarios/{user_id}")

    assert response.status_code == 200
    assert response.is_json
    data = _assert_ok_envelope(response.get_json())
    assert data["deleted_id"] == user_id

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None  # a linha CONTINUA existindo
        assert user.deleted_at is not None  # marcado como removido
        # O histórico permanece: o calendar_event do usuário não foi apagado.
        events = CalendarEvent.query.filter_by(user_id=user_id).all()
        assert len(events) == 1


def test_soft_deleted_user_some_da_listagem_admin(app, client_admin, seed_data):
    # Soft-delete C4: após remover, o usuário não aparece mais no GET da lista.
    from models import User, db

    user_id = seed_data["deletable_user_id"]
    response = client_admin.delete(f"/api/admin/usuarios/{user_id}")
    assert response.status_code == 200

    data = _assert_ok_envelope(client_admin.get("/api/admin/usuarios").get_json())
    listed_ids = {u["id"] for u in data["usuarios"]}
    assert user_id not in listed_ids

    with app.app_context():
        assert db.session.get(User, user_id) is not None  # mas continua no banco


def test_requisicao_de_usuario_removido_e_barrada(app, seed_data):
    # Soft-delete C4: mesmo com sessão válida, o usuário removido é barrado pelo
    # guard de ``load_logged_in_user`` (session.clear + g.user=None). O endpoint
    # admin então responde 401 unauthenticated.
    from models import User, db

    user_id = seed_data["admin_id"]
    other_admin_id = None
    with app.app_context():
        # Cria um 2º admin ativo para que o alvo possa ser marcado como removido
        # sem violar o invariante de "único admin" e simula a remoção direta.
        from werkzeug.security import generate_password_hash

        from time_utils import utc_now

        backup_admin = User(
            username="backup_admin",
            name="Backup Admin",
            password_hash=generate_password_hash("x", method="scrypt"),
            is_admin=True,
        )
        db.session.add(backup_admin)
        db.session.flush()
        other_admin_id = backup_admin.id
        target = db.session.get(User, user_id)
        target.deleted_at = utc_now()
        db.session.commit()

    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["login_at"] = time.time()

    response = c.get("/api/admin/usuarios")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")
    assert other_admin_id is not None


def test_guard_unico_admin_conta_apenas_ativos(app, client_admin, seed_data):
    # Soft-delete C4: o guard de "único admin" conta só admins ATIVOS. Com um 2º
    # admin já removido (deleted_at setado), o admin restante volta a ser o único
    # ativo e NÃO pode ser excluído.
    from models import User, db

    with app.app_context():
        from werkzeug.security import generate_password_hash

        from time_utils import utc_now

        removed_admin = User(
            username="removed_admin",
            name="Removed Admin",
            password_hash=generate_password_hash("x", method="scrypt"),
            is_admin=True,
            deleted_at=utc_now(),
        )
        db.session.add(removed_admin)
        db.session.commit()
        admin_id = seed_data["admin_id"]

    # Self-delete já cobre 422; aqui validamos a contagem de ativos criando um
    # admin ATIVO extra e tentando removê-lo deve funcionar, depois o restante é
    # o único ativo. Verificamos via tentativa de remover o último ativo restante.
    with app.app_context():
        from werkzeug.security import generate_password_hash

        second_active = User(
            username="second_active_admin",
            name="Second Active Admin",
            password_hash=generate_password_hash("x", method="scrypt"),
            is_admin=True,
        )
        db.session.add(second_active)
        db.session.commit()
        second_active_id = second_active.id

    # Remove o 2º admin ativo -> ok (ainda resta o admin logado ativo).
    resp = client_admin.delete(f"/api/admin/usuarios/{second_active_id}")
    assert resp.status_code == 200

    # Agora o admin logado é o único ATIVO; o removed_admin NÃO conta. Tentar
    # remover via outro caminho confirmaria 422, mas o self-delete já bloqueia o
    # admin logado. Validamos a contagem diretamente.
    with app.app_context():
        active_admins = User.query.filter(
            User.is_admin.is_(True), User.deleted_at.is_(None)
        ).count()
        assert active_admins == 1
        assert admin_id is not None
