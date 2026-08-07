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

from models import User, UserOrgao, db
from services.authorization import PAPEL_LEITOR


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
        "colecao",
    }
    # Sem ?status= na URL, o default "Vigente" é aplicado server-side.
    assert data["filters"]["status"] == "Vigente"

    options = data["options"]
    assert options["special_projects_options"] == [
        "ABEP",
        "TCE",
        "Fórum de simplificação",
    ]
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


def test_api_projetos_page_negative_or_zero_clamps_to_first_page(client_user):
    """Bug 2.20: page<=0 não deve gerar slice negativo; deve clampar para 1."""
    data_page_1 = _assert_ok_envelope(client_user.get("/api/projetos").get_json())
    data_neg = _assert_ok_envelope(client_user.get("/api/projetos?page=-1").get_json())
    data_zero = _assert_ok_envelope(client_user.get("/api/projetos?page=0").get_json())

    assert data_neg["pagination"]["page"] == 1
    assert data_zero["pagination"]["page"] == 1
    assert data_neg["projetos"] == data_page_1["projetos"]
    assert data_zero["projetos"] == data_page_1["projetos"]


def test_api_projetos_page_beyond_total_clamps_to_last_page(client_user):
    """page maior que o total de páginas deve clampar para a última página."""
    data = _assert_ok_envelope(client_user.get("/api/projetos").get_json())
    total_pages = data["pagination"]["total_pages"]

    response = client_user.get("/api/projetos?page=999999")
    data_beyond = _assert_ok_envelope(response.get_json())

    assert data_beyond["pagination"]["page"] == max(1, total_pages)


def test_api_projetos_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/projetos")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_projetos_expoe_orgaos_assignable_options_para_gestor(
    client_user, seed_data
):
    """Picker do modal Criar Projeto (§5.4): gestor mantém a própria subárvore."""
    data = _assert_ok_envelope(client_user.get("/api/projetos").get_json())
    options = data["options"]

    assignable = options["orgaos_assignable_options"]
    assert assignable, "gestor (backfill S2) deve poder atribuir a própria área"
    assert {"id", "sigla", "nome", "pai_id"} == set(assignable[0].keys())
    assert seed_data["auditoria_orgao_id"] in {o["id"] for o in assignable}


def test_api_projetos_orgaos_assignable_options_vazio_para_leitor(app, seed_data):
    """Leitor vê o filtro (visibilidade), mas não recebe órgão atribuível."""
    with app.app_context():
        user = User(username="lista_leitor", name="Lista Leitor", orgao="x")
        user.set_password("senha123")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            UserOrgao(
                user_id=user.id,
                orgao_id=seed_data["auditoria_orgao_id"],
                papel=PAPEL_LEITOR,
            )
        )
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id

    data = _assert_ok_envelope(client.get("/api/projetos").get_json())
    options = data["options"]

    assert options["orgaos_assignable_options"] == []
    assert options["orgaos_options"], "filtro da lista continua por visibilidade"


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
        "search",
        "selected_orgao",
    }
    # Opções de órgão com value = ID (o sanitizador de ?orgao= espera id; a SPA
    # derivava siglas e qualquer escolha era rejeitada com 422).
    assert isinstance(data["orgaos_options"], list)
    for option in data["orgaos_options"]:
        assert option["value"].isdigit()


def test_api_tarefas_filtra_por_orgao_valido(client_user, seed_data):
    """Regressão: escolher um órgão das próprias opções não pode dar 422."""
    data = _assert_ok_envelope(client_user.get("/api/tarefas").get_json())
    if not data["orgaos_options"]:
        return
    value = data["orgaos_options"][0]["value"]
    response = client_user.get(f"/api/tarefas?orgao={value}")
    assert response.status_code == 200
    filtered = _assert_ok_envelope(response.get_json())
    assert str(filtered["filters"]["selected_orgao"]) == value


def test_api_tarefas_pagination_shape_and_clamp(client_user):
    """A lista do hub pagina por GRUPO de projeto; página fora do intervalo clampa."""
    data = _assert_ok_envelope(client_user.get("/api/tarefas").get_json())
    assert set(data["pagination"].keys()) == {
        "page",
        "per_page",
        "total_pages",
        "total_groups",
    }
    assert data["pagination"]["page"] == 1

    clamped = _assert_ok_envelope(client_user.get("/api/tarefas?page=9999").get_json())
    total_pages = clamped["pagination"]["total_pages"]
    assert clamped["pagination"]["page"] == max(1, total_pages)


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
    data = _assert_ok_envelope(client_user.get("/api/projetos-pendentes").get_json())
    assert "orgaos_options" in data
    assert isinstance(data["orgaos_options"], list)


def test_api_projetos_pendentes_orgao_option_shape(client_user, seed_data):
    """Cada opção de órgão expõe ``value``/``label`` e o ``id`` no escopo."""
    data = _assert_ok_envelope(client_user.get("/api/projetos-pendentes").get_json())
    if not data["orgaos_options"]:
        return
    option = data["orgaos_options"][0]
    assert "value" in option
    assert "label" in option
    assert isinstance(option["value"], str)
