"""Contrato de ``GET /api/admin/relatorios/grants-orfaos`` (S4/F3-25).

Superfície do relatório de grants órfãos: ``api_admin_required`` (401/403) e
envelope canônico ``{"ok": true, "data": {"grants": [...]}}``. A lógica do
relatório em si está coberta em ``tests/test_orphan_grants_report_unit.py``.
"""

from __future__ import annotations

from typing import Any

_URL = "/api/admin/relatorios/grants-orfaos"


def _assert_ok_envelope(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    return payload["data"]


def test_grants_orfaos_requires_login(client):
    response = client.get(_URL)

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthenticated"


def test_grants_orfaos_forbidden_for_non_admin(client_user):
    response = client_user.get(_URL)

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_grants_orfaos_empty_without_invites(client_admin):
    response = client_admin.get(_URL)

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data == {"grants": []}
