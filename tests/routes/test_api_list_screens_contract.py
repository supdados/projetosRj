"""Testes de contrato dos endpoints JSON das telas de lista (Fase 3).

Afirmam o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error":
{"code", "message"}}`` de ``/api/projetos`` (Lista de Projetos) e ``/api/tarefas``
(Hub de Tarefas em modo lista), o 401 JSON do guard ``api_login_required`` quando
não há sessão e o 422 ``validation`` quando o filtro de órgão é inválido. Cobrem
ainda a extensão da Fase 3 em ``/api/projetos-pendentes``: o payload agora
entrega ``orgaos_options`` (a subárvore de órgãos visível ao usuário).

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo,
``client_user`` autenticado como ``user_auditoria`` e ``seed_data``). Sem mocks
de rede: os endpoints operam sobre a sessão e o banco de teste já semeado.
"""

from __future__ import annotations

from typing import Any


def _assert_ok_envelope(payload: Any) -> dict[str, Any]:
    """Valida o envelope de sucesso e devolve o ``data``."""
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "data" in payload
    assert "error" not in payload
    return payload["data"]


def _assert_fail_envelope(payload: Any, *, code: str) -> None:
    """Valida o envelope de erro e o ``code`` canônico esperado."""
    assert isinstance(payload, dict)
    assert payload["ok"] is False
    assert "data" not in payload
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]


# ---------------------------------------------------------------------------
# /api/projetos (Lista de Projetos)
# ---------------------------------------------------------------------------


def test_api_projetos_returns_ok_envelope_with_expected_shape(client_user):
    response = client_user.get("/api/projetos")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["projetos"], list)

    assert set(data["filters"].keys()) == {
        "status",
        "prioridade",
        "atraso",
        "special_project",
        "delivery_type",
        "abep_indicator",
        "objetivo",
        "q",
        "selected_orgao",
    }
    # Sem ?status= na URL, o default "Vigente" é aplicado server-side.
    assert data["filters"]["status"] == "Vigente"

    options = data["options"]
    assert options["special_projects_options"] == ["ABEP", "TCE"]
    assert isinstance(options["abep_indicadores_options"], list)
    assert isinstance(options["orgaos_options"], list)

    assert set(data["pagination"].keys()) == {
        "page",
        "per_page",
        "total",
        "total_pages",
    }
    assert data["pagination"]["per_page"] == 40


def test_api_projetos_card_reuses_serializer_without_secrets(client_user):
    """Cada projeto expõe um card serializado, sem segredos."""
    data = _assert_ok_envelope(client_user.get("/api/projetos?status=").get_json())
    if not data["projetos"]:
        return
    card = data["projetos"][0]
    assert "id" in card
    assert "titulo" in card
    assert "password_hash" not in card


def test_api_projetos_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/projetos")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_projetos_invalid_orgao_filter_returns_422_envelope(client_user):
    """Filtro de órgão fora do escopo => 422 ``validation`` (não 302)."""
    response = client_user.get("/api/projetos?orgao=999999")

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


# ---------------------------------------------------------------------------
# /api/tarefas (Hub de Tarefas em modo lista)
# ---------------------------------------------------------------------------


def test_api_tarefas_returns_ok_envelope_with_expected_shape(client_user):
    response = client_user.get("/api/tarefas")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["groups"], list)
    assert isinstance(data["project_options"], list)
    assert data["include_archived"] is False
    assert "total_items" in data
    assert set(data["filters"].keys()) == {
        "project",
        "prioridade",
        "tipo",
        "status",
        "responsavel",
        "selected_orgao",
    }


def test_api_tarefas_group_reuses_task_card_serializer(client_user):
    """Cada grupo expõe tarefas serializadas (card), sem segredos."""
    data = _assert_ok_envelope(client_user.get("/api/tarefas").get_json())
    if not data["groups"]:
        return
    group = data["groups"][0]
    assert "project_titulo" in group
    assert isinstance(group["tasks"], list)
    if group["tasks"]:
        card = group["tasks"][0]
        assert "id" in card
        assert "descricao" in card
        assert "password_hash" not in card


def test_api_tarefas_arquivadas_mode_sets_include_archived(client_user):
    data = _assert_ok_envelope(
        client_user.get("/api/tarefas?modo=arquivadas").get_json()
    )
    assert data["include_archived"] is True


def test_api_tarefas_finalizadas_mode_filters_by_status(client_user):
    data = _assert_ok_envelope(
        client_user.get("/api/tarefas?modo=finalizadas").get_json()
    )
    assert data["include_archived"] is False
    assert data["filters"]["status"] == "finalizada"


def test_api_tarefas_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/tarefas")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_tarefas_invalid_orgao_filter_returns_422_envelope(client_user):
    """Filtro de órgão fora do escopo => 422 ``validation`` (não 302)."""
    response = client_user.get("/api/tarefas?orgao=999999")

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


# ---------------------------------------------------------------------------
# /api/projetos-pendentes — extensão Fase 3 (orgaos_options)
# ---------------------------------------------------------------------------


def test_api_projetos_pendentes_now_returns_orgaos_options(client_user):
    """O payload de Pendentes passa a entregar ``orgaos_options`` (subárvore)."""
    data = _assert_ok_envelope(
        client_user.get("/api/projetos-pendentes").get_json()
    )
    assert "orgaos_options" in data
    assert isinstance(data["orgaos_options"], list)


def test_api_projetos_pendentes_orgao_option_shape(client_user, seed_data):
    """Cada opção de órgão expõe ``value``/``label`` e o ``id`` no escopo."""
    data = _assert_ok_envelope(
        client_user.get("/api/projetos-pendentes").get_json()
    )
    if not data["orgaos_options"]:
        return
    option = data["orgaos_options"][0]
    assert "value" in option
    assert "label" in option
    assert isinstance(option["value"], str)
