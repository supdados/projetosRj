"""Testes de contrato dos endpoints JSON Admin de Usuários (envelope canônico).

Cobrem o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error": {...}}``
de ``/api/admin/usuarios*`` e os guards de ``api_admin_required`` (401 sem
sessão, 403 para usuário comum) além das validações 422.

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo, ``client_user``
não-admin e ``client_admin``). NUNCA deve vazar ``password_hash``/``govbr_sub``.
"""

from __future__ import annotations

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


def test_list_returns_ok_envelope_with_meta(client_admin, seed_data):
    response = client_admin.get("/api/admin/usuarios")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["usuarios"], list)
    assert data["usuarios"]
    meta = response.get_json()["meta"]
    assert set(meta.keys()) == {"page", "per_page", "total", "total_pages"}
    assert meta["per_page"] == 10


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
# POST /api/admin/usuarios/<id> (editar)
# ---------------------------------------------------------------------------


def test_update_returns_ok_envelope(client_admin, seed_data):
    user_id = seed_data["editable_user_id"]
    response = client_admin.post(
        f"/api/admin/usuarios/{user_id}",
        json={"name": "Nome Atualizado Contrato", "orgao": "Novo Orgao"},
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["usuario"]["name"] == "Nome Atualizado Contrato"


def test_update_returns_404_for_unknown_user(client_admin):
    response = client_admin.post("/api/admin/usuarios/999999", json={"name": "x"})
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_update_invalid_cpf_returns_422(client_admin, seed_data):
    response = client_admin.post(
        f"/api/admin/usuarios/{seed_data['editable_user_id']}",
        json={"name": "Nome", "cpf_govbr": "123"},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_update_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/usuarios/{seed_data['editable_user_id']}", json={"name": "x"}
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


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
# POST /api/admin/usuarios/<id>/delete
# ---------------------------------------------------------------------------


def test_delete_returns_ok_envelope(client_admin, seed_data):
    user_id = seed_data["deletable_user_id"]
    response = client_admin.post(f"/api/admin/usuarios/{user_id}/delete")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["deleted_id"] == user_id


def test_delete_self_returns_422(client_admin, seed_data):
    response = client_admin.post(
        f"/api/admin/usuarios/{seed_data['admin_id']}/delete"
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_delete_returns_404_for_unknown_user(client_admin):
    response = client_admin.post("/api/admin/usuarios/999999/delete")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_delete_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/usuarios/{seed_data['deletable_user_id']}/delete"
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


def test_delete_user_com_evento_de_calendario_retorna_409_json(
    app, client_admin, seed_data
):
    # Regressão: usuário com ``calendar_event`` (user_id NOT NULL) dispara
    # IntegrityError no delete. Sem try/except a exceção vazava como HTML 500 e o
    # cliente da SPA quebrava ("Unrecognized token '<'"). Deve devolver 409 JSON.
    from datetime import datetime

    from models import CalendarEvent, db

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

    response = client_admin.post(f"/api/admin/usuarios/{user_id}/delete")

    assert response.status_code == 409
    assert response.is_json  # NÃO pode vazar HTML
    _assert_fail_envelope(response.get_json(), code="conflict")
