"""Testes de contrato dos endpoints JSON Admin de Órgãos (read-only).

A estrutura organizacional é espelho do SIORG-RJ: as rotas de escrita de
``/api/admin/orgaos*`` foram cortadas, junto com os GETs do catálogo local de
tipos e os campos ``tipos``/``tipo_rank``/``candidatos_pai`` (sem consumidor
na SPA). Restam os GETs de visualização, no envelope ``{"ok": true, "data":
...}`` / ``{"ok": false, "error": {...}}``, protegidos por
``api_admin_required`` (401 sem sessão, 403 para não-admin).

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
# GET /api/admin/orgaos (árvore)
# ---------------------------------------------------------------------------


def test_tree_returns_ok_envelope_with_recursive_children(client_admin, seed_data):
    response = client_admin.get("/api/admin/orgaos")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["arvore"], list)
    assert isinstance(data["max_depth"], int)
    assert data["total"] >= 1
    # Catálogo local de tipos cortado: payload não carrega mais esses campos.
    assert "tipos" not in data
    assert "tipo_rank" not in data
    assert "candidatos_pai" not in data

    raiz = next(n for n in data["arvore"] if n["id"] == seed_data["orgao_root_id"])
    assert "filhos" in raiz
    child_ids = {f["id"] for f in raiz["filhos"]}
    assert seed_data["orgao_child_id"] in child_ids


def test_tree_nodes_expose_codigo_externo(client_admin, seed_data):
    # O chip "não oficial" da SPA depende de codigo_externo em CADA nó.
    response = client_admin.get("/api/admin/orgaos")
    data = _assert_ok_envelope(response.get_json())

    def _walk(nos):
        for no in nos:
            yield no
            yield from _walk(no["filhos"])

    for no in _walk(data["arvore"]):
        assert "codigo_externo" in no


def test_tree_returns_401_when_unauthenticated(client):
    response = client.get("/api/admin/orgaos")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_tree_returns_403_for_non_admin(client_user):
    response = client_user.get("/api/admin/orgaos")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# GET /api/admin/orgaos/<id> (detalhe read-only)
# ---------------------------------------------------------------------------


def test_detail_returns_orgao_read_only(client_admin, seed_data):
    orgao_id = seed_data["orgao_child_id"]
    response = client_admin.get(f"/api/admin/orgaos/{orgao_id}")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["orgao"]["id"] == orgao_id
    assert data["is_root"] is False
    # Estrutura read-only espelho do SIORG: sem candidatos a pai/catálogos.
    assert "candidatos_pai" not in data
    assert "tipos" not in data


def test_detail_returns_404_for_unknown_orgao(client_admin):
    response = client_admin.get("/api/admin/orgaos/999999")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_detail_returns_403_for_non_admin(client_user, seed_data):
    response = client_user.get(f"/api/admin/orgaos/{seed_data['orgao_child_id']}")
    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")
