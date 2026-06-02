"""Testes de contrato dos endpoints JSON Admin de Órgãos/Tipos (envelope).

Cobrem o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error": {...}}``
de ``/api/admin/orgaos*`` e ``/api/admin/orgaos/tipos*``, os guards de
``api_admin_required`` (401 sem sessão, 403 para usuário comum) e as validações
de negócio reaproveitadas das rotas Jinja (hierarquia de tipos, níveis,
profundidade, proteções de exclusão/desativação).

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo,
``client_user`` não-admin e ``client_admin``). NUNCA deve vazar segredos.
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
# GET /api/admin/orgaos (árvore + catálogos)
# ---------------------------------------------------------------------------


def test_tree_returns_ok_envelope_with_recursive_children(client_admin, seed_data):
    response = client_admin.get("/api/admin/orgaos")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["arvore"], list)
    assert isinstance(data["tipos"], list)
    assert isinstance(data["candidatos_pai"], list)
    assert isinstance(data["tipo_rank"], dict)
    assert isinstance(data["max_depth"], int)
    assert data["total"] >= 1

    raiz = next(n for n in data["arvore"] if n["id"] == seed_data["orgao_root_id"])
    assert "filhos" in raiz
    child_ids = {f["id"] for f in raiz["filhos"]}
    assert seed_data["orgao_child_id"] in child_ids


def test_tree_returns_401_when_unauthenticated(client):
    response = client.get("/api/admin/orgaos")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_tree_returns_403_for_non_admin(client_user):
    response = client_user.get("/api/admin/orgaos")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# GET /api/admin/orgaos/<id> (form data)
# ---------------------------------------------------------------------------


def test_detail_returns_orgao_and_candidate_pais(client_admin, seed_data):
    orgao_id = seed_data["orgao_child_id"]
    response = client_admin.get(f"/api/admin/orgaos/{orgao_id}")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["orgao"]["id"] == orgao_id
    assert data["is_root"] is False
    assert isinstance(data["candidatos_pai"], list)
    # o próprio órgão não pode ser candidato a pai de si mesmo
    assert orgao_id not in {p["id"] for p in data["candidatos_pai"]}


def test_detail_returns_404_for_unknown_orgao(client_admin):
    response = client_admin.get("/api/admin/orgaos/999999")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_detail_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.get(f"/api/admin/orgaos/{seed_data['orgao_child_id']}")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos (criar)
# ---------------------------------------------------------------------------


def test_create_returns_ok_envelope(client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/orgaos",
        json={
            "nome": "Secretaria de Contrato",
            "sigla": "SCONT",
            "tipo_id": seed_data["orgao_tipo_secretaria_id"],
            "pai_id": seed_data["orgao_root_id"],
            "ordem": 0,
            "ativo": "1",
        },
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["orgao"]["sigla"] == "SCONT"
    assert data["orgao"]["pai_id"] == seed_data["orgao_root_id"]
    assert "filhos" not in data["orgao"]


def test_create_missing_required_fields_returns_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/orgaos",
        json={"nome": "", "sigla": "", "pai_id": seed_data["orgao_root_id"]},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_create_invalid_parent_hierarchy_returns_422(client_admin, seed_data):
    # Secretaria (nível 1) não pode ser pai de outra Secretaria (nível 1).
    response = client_admin.post(
        "/api/admin/orgaos",
        json={
            "nome": "Secretaria Filha Invalida",
            "sigla": "SFINV",
            "tipo_id": seed_data["orgao_tipo_secretaria_id"],
            "pai_id": seed_data["orgao_child_id"],
        },
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_create_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        "/api/admin/orgaos",
        json={
            "nome": "X",
            "sigla": "X",
            "tipo_id": seed_data["orgao_tipo_secretaria_id"],
            "pai_id": seed_data["orgao_root_id"],
        },
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/<id> (editar)
# ---------------------------------------------------------------------------


def test_update_returns_ok_envelope(client_admin, seed_data):
    orgao_id = seed_data["orgao_child_id"]
    response = client_admin.post(
        f"/api/admin/orgaos/{orgao_id}",
        json={
            "nome": "Secretaria Renomeada",
            "sigla": "SECT",
            "tipo_id": seed_data["orgao_tipo_secretaria_id"],
            "pai_id": seed_data["orgao_root_id"],
            "ordem": 0,
            "ativo": "1",
        },
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["orgao"]["nome"] == "Secretaria Renomeada"


def test_update_returns_404_for_unknown_orgao(client_admin):
    response = client_admin.post("/api/admin/orgaos/999999", json={"nome": "x"})
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_update_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/orgaos/{seed_data['orgao_child_id']}", json={"nome": "x"}
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/<id>/move
# ---------------------------------------------------------------------------


def test_move_returns_ok_envelope(client_admin, seed_data):
    orgao_id = seed_data["orgao_child_id"]
    response = client_admin.post(
        f"/api/admin/orgaos/{orgao_id}/move",
        json={"pai_id": seed_data["orgao_root_id"]},
    )
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["orgao"]["pai_id"] == seed_data["orgao_root_id"]


def test_move_to_root_invalid_for_non_root_tipo_returns_409(client_admin, seed_data):
    # Secretaria não é permitida para raiz; mover para pai None deve falhar.
    response = client_admin.post(
        f"/api/admin/orgaos/{seed_data['orgao_child_id']}/move",
        json={"pai_id": None},
    )
    assert response.status_code == 409
    _assert_fail_envelope(response.get_json(), code="validation")


def test_move_returns_404_for_unknown_orgao(client_admin, seed_data):
    response = client_admin.post(
        "/api/admin/orgaos/999999/move",
        json={"pai_id": seed_data["orgao_root_id"]},
    )
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/<id>/reorder
# ---------------------------------------------------------------------------


def test_reorder_invalid_direction_returns_422(client_admin, seed_data):
    response = client_admin.post(
        f"/api/admin/orgaos/{seed_data['orgao_child_id']}/reorder",
        json={"direction": "sideways"},
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_reorder_ok_envelope_at_edge_is_idempotent(client_admin, seed_data):
    response = client_admin.post(
        f"/api/admin/orgaos/{seed_data['orgao_child_id']}/reorder",
        json={"direction": "up"},
    )
    assert response.status_code == 200
    _assert_ok_envelope(response.get_json())


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/<id>/toggle-ativo
# ---------------------------------------------------------------------------


def test_toggle_ativo_returns_ok_envelope(client_admin, seed_data):
    orgao_id = seed_data["orgao_child_id"]
    before = client_admin.get(f"/api/admin/orgaos/{orgao_id}").get_json()["data"][
        "orgao"
    ]["ativo"]
    response = client_admin.post(f"/api/admin/orgaos/{orgao_id}/toggle-ativo")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["orgao"]["ativo"] is (not before)


def test_toggle_ativo_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/orgaos/{seed_data['orgao_child_id']}/toggle-ativo"
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/<id>/delete
# ---------------------------------------------------------------------------


def test_delete_leaf_returns_ok_envelope(client_admin, seed_data):
    orgao_id = seed_data["orgao_child_id"]
    response = client_admin.post(f"/api/admin/orgaos/{orgao_id}/delete")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["deleted_id"] == orgao_id


def test_delete_root_returns_409(client_admin, seed_data):
    response = client_admin.post(
        f"/api/admin/orgaos/{seed_data['orgao_root_id']}/delete"
    )
    assert response.status_code == 409
    _assert_fail_envelope(response.get_json(), code="validation")


def test_delete_orgao_with_children_returns_409(client_admin, seed_data):
    # O root tem o child como filho; não pode ser excluído (também é raiz).
    response = client_admin.post(
        f"/api/admin/orgaos/{seed_data['orgao_root_id']}/delete"
    )
    assert response.status_code == 409
    _assert_fail_envelope(response.get_json(), code="validation")


def test_delete_returns_404_for_unknown_orgao(client_admin):
    response = client_admin.post("/api/admin/orgaos/999999/delete")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


# ---------------------------------------------------------------------------
# GET /api/admin/orgaos/tipos (lista)
# ---------------------------------------------------------------------------


def test_tipos_list_returns_ok_envelope(client_admin):
    response = client_admin.get("/api/admin/orgaos/tipos")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["tipos"], list)
    assert data["tipos"]
    assert isinstance(data["usage_counts"], dict)
    for tipo in data["tipos"]:
        assert "nome" in tipo
        assert "nivel" in tipo
        assert "permite_raiz" in tipo


def test_tipos_list_returns_401_when_unauthenticated(client):
    response = client.get("/api/admin/orgaos/tipos")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_tipos_list_returns_403_for_non_admin(client_user):
    response = client_user.get("/api/admin/orgaos/tipos")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# GET /api/admin/orgaos/tipos/<id>
# ---------------------------------------------------------------------------


def test_tipo_detail_returns_ok_envelope(client_admin, seed_data):
    tipo_id = seed_data["orgao_tipo_secretaria_id"]
    response = client_admin.get(f"/api/admin/orgaos/tipos/{tipo_id}")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["tipo"]["id"] == tipo_id


def test_tipo_detail_returns_404_for_unknown(client_admin):
    response = client_admin.get("/api/admin/orgaos/tipos/999999")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/tipos (criar)
# ---------------------------------------------------------------------------


def test_tipo_create_returns_ok_envelope(client_admin):
    response = client_admin.post(
        "/api/admin/orgaos/tipos",
        json={"nome": "Divisao Contrato", "nivel": 4, "ativo": "1"},
    )
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["tipo"]["nome"] == "Divisao Contrato"
    assert data["tipo"]["is_system"] is False


def test_tipo_create_missing_name_returns_422(client_admin):
    response = client_admin.post(
        "/api/admin/orgaos/tipos", json={"nome": "", "nivel": 4}
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_tipo_create_duplicate_returns_422(client_admin):
    response = client_admin.post(
        "/api/admin/orgaos/tipos", json={"nome": "Secretaria", "nivel": 1}
    )
    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/tipos/<id> (editar)
# ---------------------------------------------------------------------------


def test_tipo_update_returns_ok_envelope(client_admin, seed_data):
    tipo_id = seed_data["orgao_tipo_secretaria_id"]
    response = client_admin.post(
        f"/api/admin/orgaos/tipos/{tipo_id}",
        json={
            "nome": "Secretaria",
            "nivel": 1,
            "descricao": "Atualizada",
            "ativo": "1",
            # Secretaria é o tipo do órgão-raiz semeado; manter permite_raiz
            # evita disparar _invalid_orgao_type_level_changes (409 hierárquico).
            "permite_raiz": "1",
        },
    )
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["tipo"]["descricao"] == "Atualizada"


def test_tipo_update_deactivate_in_use_returns_409(client_admin, seed_data):
    # Secretaria está em uso por SECT; desativar deve ser bloqueado.
    tipo_id = seed_data["orgao_tipo_secretaria_id"]
    response = client_admin.post(
        f"/api/admin/orgaos/tipos/{tipo_id}",
        json={"nome": "Secretaria", "nivel": 1},
    )
    assert response.status_code == 409
    _assert_fail_envelope(response.get_json(), code="validation")


def test_tipo_update_returns_404_for_unknown(client_admin):
    response = client_admin.post(
        "/api/admin/orgaos/tipos/999999", json={"nome": "x", "nivel": 1}
    )
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/tipos/<id>/toggle-ativo
# ---------------------------------------------------------------------------


def test_tipo_toggle_ativo_returns_ok_envelope(client_admin, seed_data):
    tipo_id = seed_data["orgao_tipo_nucleo_id"]
    response = client_admin.post(f"/api/admin/orgaos/tipos/{tipo_id}/toggle-ativo")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["tipo"]["ativo"] is False


def test_tipo_toggle_ativo_root_tipo_returns_409(client_admin, seed_data):
    # Estado é permite_raiz e ativo; não pode ser desativado.
    estado_id = client_admin.get("/api/admin/orgaos/tipos").get_json()["data"]
    estado_id = next(
        t["id"] for t in estado_id["tipos"] if t["permite_raiz"] and t["ativo"]
    )
    response = client_admin.post(f"/api/admin/orgaos/tipos/{estado_id}/toggle-ativo")
    assert response.status_code == 409
    _assert_fail_envelope(response.get_json(), code="validation")


# ---------------------------------------------------------------------------
# POST /api/admin/orgaos/tipos/<id>/delete
# ---------------------------------------------------------------------------


def test_tipo_delete_unused_returns_ok_envelope(client_admin, seed_data):
    tipo_id = seed_data["orgao_tipo_nucleo_id"]
    response = client_admin.post(f"/api/admin/orgaos/tipos/{tipo_id}/delete")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["deleted_id"] == tipo_id


def test_tipo_delete_in_use_returns_409(client_admin, seed_data):
    tipo_id = seed_data["orgao_tipo_secretaria_id"]
    response = client_admin.post(f"/api/admin/orgaos/tipos/{tipo_id}/delete")
    assert response.status_code == 409
    _assert_fail_envelope(response.get_json(), code="validation")


def test_tipo_delete_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.post(
        f"/api/admin/orgaos/tipos/{seed_data['orgao_tipo_nucleo_id']}/delete"
    )
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")
