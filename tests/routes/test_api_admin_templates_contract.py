"""Testes de contrato dos endpoints JSON Admin de Modelos de Etapas (envelope).

Cobrem o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error": {...}}``
de ``/api/admin/templates*``, os guards de ``api_admin_required`` (401 sem
sessão, 403 para usuário comum) e as validações reaproveitadas do fluxo Jinja
(nome + ao menos uma etapa obrigatórios) que retornam 422.

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo,
``client_user`` não-admin, ``client_admin`` e ``seed_data``).
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
# GET /api/admin/templates (lista + métricas)
# ---------------------------------------------------------------------------


def test_list_returns_ok_envelope_with_metrics(client_admin, seed_data):
    response = client_admin.get("/api/admin/templates")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["templates"], list)
    assert data["templates"]
    assert isinstance(data["order_options"], list)

    row = next(t for t in data["templates"] if t["id"] == seed_data["template_id"])
    assert row["name"] == "Template Base"
    assert row["stage_count"] == 2
    assert row["total_duration"] == 5
    assert "usage_count" in row
    assert "silhouette" not in row


def test_list_respects_order_query(client_admin, seed_data):
    response = client_admin.get("/api/admin/templates?order=nome&q=Base&page=1")
    assert response.status_code == 200
    payload = response.get_json()
    _assert_ok_envelope(payload)
    assert payload["meta"]["order"] == "nome"
    assert payload["meta"]["q"] == "Base"
    assert payload["meta"]["page"] == 1


def test_list_returns_401_when_unauthenticated(client):
    response = client.get("/api/admin/templates")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_list_returns_403_for_non_admin(client_user):
    response = client_user.get("/api/admin/templates")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# GET /api/admin/templates/<id> (form + etapas)
# ---------------------------------------------------------------------------


def test_detail_returns_template_with_stages(client_admin, seed_data):
    template_id = seed_data["template_id"]
    response = client_admin.get(f"/api/admin/templates/{template_id}")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    template = data["template"]
    assert template["id"] == template_id
    assert template["stage_count"] == 2
    assert [s["name"] for s in template["stages"]] == ["Planejamento", "Execucao"]
    assert template["stages"][0]["order"] == 0
    assert "usage_count" in data


def test_detail_returns_404_for_unknown(client_admin):
    response = client_admin.get("/api/admin/templates/999999")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_detail_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.get(f"/api/admin/templates/{seed_data['template_id']}")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/templates (criar)
# ---------------------------------------------------------------------------


def test_create_returns_ok_envelope(client_admin):
    response = client_admin.post(
        "/api/admin/templates",
        json={
            "name": "Template de Contrato",
            "description": "Criado no teste",
            "stages": [
                {"name": "Levantamento", "duration_days": 3},
                {"name": "Validacao", "duration_days": 2},
            ],
        },
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    template = data["template"]
    assert template["name"] == "Template de Contrato"
    assert template["stage_count"] == 2
    assert template["total_duration"] == 5


def test_create_missing_name_returns_422(client_admin):
    response = client_admin.post(
        "/api/admin/templates",
        json={"name": "", "stages": [{"name": "Etapa", "duration_days": 1}]},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_create_without_stages_returns_422(client_admin):
    response = client_admin.post(
        "/api/admin/templates",
        json={"name": "Sem Etapas", "stages": []},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_create_returns_403_for_non_admin(client_user):
    response = client_user.post(
        "/api/admin/templates",
        json={"name": "X", "stages": [{"name": "Etapa", "duration_days": 1}]},
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/templates/<id> (editar)
# ---------------------------------------------------------------------------


def test_update_replaces_stages(client_admin, seed_data):
    template_id = seed_data["template_id"]
    response = client_admin.post(
        f"/api/admin/templates/{template_id}",
        json={
            "name": "Template Renomeado",
            "description": "Atualizado",
            "stages": [{"name": "Unica Etapa", "duration_days": 7}],
        },
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    template = data["template"]
    assert template["name"] == "Template Renomeado"
    assert template["stage_count"] == 1
    assert template["stages"][0]["name"] == "Unica Etapa"
    assert template["total_duration"] == 7


def test_update_without_stages_returns_422(client_admin, seed_data):
    response = client_admin.post(
        f"/api/admin/templates/{seed_data['template_id']}",
        json={"name": "Sem Etapas", "stages": []},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_update_returns_404_for_unknown(client_admin):
    response = client_admin.post(
        "/api/admin/templates/999999",
        json={"name": "x", "stages": [{"name": "e", "duration_days": 1}]},
    )
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_update_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/templates/{seed_data['template_id']}",
        json={"name": "x", "stages": [{"name": "e", "duration_days": 1}]},
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/templates/<id>/duplicate
# ---------------------------------------------------------------------------


def test_duplicate_returns_copy_with_stages(client_admin, seed_data):
    template_id = seed_data["template_id"]
    response = client_admin.post(f"/api/admin/templates/{template_id}/duplicate")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    copy = data["template"]
    assert copy["id"] != template_id
    assert copy["name"].endswith("(cópia)")
    assert copy["stage_count"] == 2


def test_duplicate_returns_404_for_unknown(client_admin):
    response = client_admin.post("/api/admin/templates/999999/duplicate")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_duplicate_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/templates/{seed_data['template_id']}/duplicate"
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/templates/<id>/delete
# ---------------------------------------------------------------------------


def test_delete_returns_ok_envelope(client_admin, seed_data):
    template_id = seed_data["template_id"]
    response = client_admin.post(f"/api/admin/templates/{template_id}/delete")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["deleted_id"] == template_id


def test_delete_returns_404_for_unknown(client_admin):
    response = client_admin.post("/api/admin/templates/999999/delete")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_delete_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/templates/{seed_data['template_id']}/delete"
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")
