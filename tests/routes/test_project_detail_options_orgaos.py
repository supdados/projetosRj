"""Contrato: ``options.orgaos`` no payload de ``GET /api/projetos/<id>/detalhe``.

O picker de Área Responsável (Detalhe SPA) lê os órgãos escopados de
``data.options.orgaos`` — escopo de ESCRITA (``scoped_orgao_options``: rank >=
editor na subárvore, sempre ativos). Estes testes fixam a presença e o shape
``{id, sigla, nome, pai_id}`` (``pai_id`` alimenta a árvore do OrgaoTreeSelect),
além de garantir que o admin enxerga mais órgãos que um não-admin restrito à
própria subtree.

Reusa as fixtures de ``tests/conftest.py`` (``client_user`` = user_auditoria,
``client_admin`` = admin) sobre o banco semeado.
"""

from __future__ import annotations

from typing import Any


def _detail_options(client, project_id: int) -> dict[str, Any]:
    response = client.get(f"/api/projetos/{project_id}/detalhe")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    return payload["data"]["options"]


def test_options_include_orgaos_with_expected_shape(client_user, seed_data):
    options = _detail_options(client_user, seed_data["project_id"])

    assert "orgaos" in options
    orgaos = options["orgaos"]
    assert isinstance(orgaos, list)
    assert orgaos, "user_auditoria possui vínculo, então a lista não pode ser vazia"
    for orgao in orgaos:
        assert set(orgao.keys()) == {"id", "sigla", "nome", "pai_id"}
        assert isinstance(orgao["id"], int)
        assert isinstance(orgao["sigla"], str)
        assert isinstance(orgao["nome"], str)
        assert orgao["pai_id"] is None or isinstance(orgao["pai_id"], int)


def test_options_orgaos_sorted_by_sigla(client_user, seed_data):
    orgaos = _detail_options(client_user, seed_data["project_id"])["orgaos"]
    siglas = [o["sigla"] for o in orgaos]
    assert siglas == sorted(siglas)


def test_admin_sees_more_orgaos_than_scoped_user(client_admin, client_user, seed_data):
    admin_orgaos = _detail_options(client_admin, seed_data["project_id"])["orgaos"]
    user_orgaos = _detail_options(client_user, seed_data["project_id"])["orgaos"]

    admin_ids = {o["id"] for o in admin_orgaos}
    user_ids = {o["id"] for o in user_orgaos}

    assert user_ids, "não-admin com vínculo deve ver ao menos seu próprio órgão"
    assert user_ids.issubset(admin_ids)
    assert len(admin_ids) > len(user_ids)
