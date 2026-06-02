"""Testes de contrato dos endpoints /api de PARIDADE (mutações da SPA).

Afirmam o envelope canônico (``{ok, data}`` / ``{ok, error: {code, message}}``),
o 401 do guard ``api_login_required`` sem sessão e os 403/404/422 estruturados
das novas rotas:

    - ``POST /api/projetos`` / ``POST /api/projetos/<id>/concluir``
    - ``GET  /api/catalogos/objetivos``
    - ``GET  /api/projetos/<pid>/etapas/<eid>/tarefas``
    - ``POST /api/tarefas`` / ``/api/tarefas/<id>/excluir`` /
      ``/api/tarefas/<id>/mover-etapa`` / ``/api/tarefas/arquivar-finalizadas`` /
      ``GET /api/tarefas/sugestoes-responsavel``
    - ``POST /api/calendarios/eventos[/<id>/editar|/excluir|/gerar-meet]``
    - ``POST /api/projetos/<id>/reunioes`` / ``POST /api/etapas/<id>/reuniao``

Reusa as fixtures de ``tests/conftest.py`` (``client`` anônimo, ``client_user``,
``client_outsider`` e ``seed_data``). Sem rede: as ações de Google falham
graciosamente (sem conexão ativa no seed).
"""

from __future__ import annotations

from typing import Any


def _ok(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "data" in payload
    assert "error" not in payload
    return payload["data"]


def _fail(payload: Any, *, code: str) -> None:
    assert isinstance(payload, dict)
    assert payload["ok"] is False
    assert "data" not in payload
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]


# ── 401 sem sessão (amostra das rotas) ────────────────────────────────────────


def test_api_parity_routes_require_login(client, seed_data):
    routes = [
        ("POST", "/api/projetos"),
        ("POST", f"/api/projetos/{seed_data['project_complete_id']}/concluir"),
        ("GET", "/api/catalogos/objetivos"),
        ("POST", "/api/tarefas"),
        ("POST", f"/api/tarefas/{seed_data['task_id']}/excluir"),
        ("POST", "/api/tarefas/arquivar-finalizadas"),
        ("GET", "/api/tarefas/sugestoes-responsavel"),
        ("POST", "/api/calendarios/eventos"),
        ("POST", f"/api/projetos/{seed_data['project_id']}/reunioes"),
        ("POST", f"/api/etapas/{seed_data['etapa_id']}/reuniao"),
    ]
    for method, path in routes:
        response = client.open(path, method=method, json={})
        assert response.status_code == 401, path
        _fail(response.get_json(), code="unauthenticated")


# ── Criar projeto ─────────────────────────────────────────────────────────────


def test_api_projeto_criar_success(client_user, seed_data):
    response = client_user.post(
        "/api/projetos",
        json={
            "titulo": "Projeto Contrato",
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "prioridade": "alta",
        },
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert isinstance(data["id"], int)
    assert data["redirect_to"] == f"/projetos/{data['id']}"
    assert data["message"] == "Projeto adicionado com sucesso!"
    assert data["project"]["id"] == data["id"]


def test_api_projeto_criar_requires_titulo(client_user, seed_data):
    response = client_user.post(
        "/api/projetos", json={"orgao_id": str(seed_data["auditoria_orgao_id"])}
    )
    assert response.status_code == 422
    _fail(response.get_json(), code="validation")


def test_api_projeto_criar_forbidden_orgao(client_outsider, seed_data):
    response = client_outsider.post(
        "/api/projetos",
        json={
            "titulo": "Fora do escopo",
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
        },
    )
    assert response.status_code == 403
    _fail(response.get_json(), code="forbidden")


# ── Concluir projeto ──────────────────────────────────────────────────────────


def test_api_projeto_concluir_success(client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_complete_id']}/concluir"
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["status"] == "Finalizado"
    assert data["redirect_to"] == f"/projetos/{seed_data['project_complete_id']}"
    assert "concluído" in data["message"]


def test_api_projeto_concluir_blocks_incomplete_stages(client_user, seed_data):
    # ``project_id`` tem etapas não concluídas => 400 validação (mesma regra legada).
    response = client_user.post(f"/api/projetos/{seed_data['project_id']}/concluir")
    assert response.status_code == 400
    _fail(response.get_json(), code="validation")


def test_api_projeto_concluir_forbidden(client_outsider, seed_data):
    response = client_outsider.post(
        f"/api/projetos/{seed_data['project_complete_id']}/concluir"
    )
    assert response.status_code == 403
    _fail(response.get_json(), code="forbidden")


def test_api_projeto_concluir_not_found(client_user):
    response = client_user.post("/api/projetos/999999/concluir")
    assert response.status_code == 404
    _fail(response.get_json(), code="not_found")


# ── Catálogo de objetivos + tarefas da etapa ──────────────────────────────────


def test_api_catalogo_objetivos(client_user):
    response = client_user.get("/api/catalogos/objetivos")
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert isinstance(data, list)
    assert all("id" in o and "descricao" in o for o in data)


def test_api_etapa_tarefas_envelope(client_user, seed_data):
    response = client_user.get(
        f"/api/projetos/{seed_data['project_id']}/etapas/{seed_data['etapa_id']}/tarefas"
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert isinstance(data["tarefas"], list)
    assert "total" in data and "done" in data


def test_api_etapa_tarefas_forbidden(client_outsider, seed_data):
    response = client_outsider.get(
        f"/api/projetos/{seed_data['project_id']}/etapas/{seed_data['etapa_id']}/tarefas"
    )
    assert response.status_code == 403
    _fail(response.get_json(), code="forbidden")


# ── Criar / excluir / mover tarefa ────────────────────────────────────────────


def test_api_tarefa_criar_success(client_user, seed_data):
    response = client_user.post(
        "/api/tarefas",
        json={"project": str(seed_data["project_id"]), "descricao": "Nova tarefa"},
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["task"]["descricao"] == "Nova tarefa"
    assert data["task"]["project_id"] == seed_data["project_id"]


def test_api_tarefa_criar_aceita_project_id_inteiro(client_user, seed_data):
    # Regressão: a SPA envia ``project_id``/``etapa_id`` como INTEIRO (JSON number);
    # o resolver fazia ``.strip()`` direto e estourava AttributeError -> HTTP 500
    # (HTML), quebrando o quick-add. Deve resolver o projeto e criar a tarefa.
    response = client_user.post(
        "/api/tarefas",
        json={
            "project_id": seed_data["project_id"],
            "etapa_id": seed_data["etapa_id"],
            "descricao": "Tarefa via id inteiro",
        },
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["task"]["project_id"] == seed_data["project_id"]


def test_api_tarefa_criar_requires_descricao(client_user, seed_data):
    response = client_user.post(
        "/api/tarefas", json={"project": str(seed_data["project_id"])}
    )
    assert response.status_code == 422
    _fail(response.get_json(), code="validation")


def test_api_tarefa_excluir_success(client_user, seed_data):
    response = client_user.post(f"/api/tarefas/{seed_data['task_id']}/excluir")
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["item_id"] == seed_data["task_id"]


def test_api_tarefa_excluir_forbidden(client_outsider, seed_data):
    # outsider vê a foreign_task mas não é autor dela? foreign_task é dele.
    # Para 403, tenta excluir a task da Auditoria (não é autor nem admin).
    response = client_outsider.post(f"/api/tarefas/{seed_data['task_id']}/excluir")
    assert response.status_code in (403, 404)
    code = "forbidden" if response.status_code == 403 else "not_found"
    _fail(response.get_json(), code=code)


def test_api_tarefa_mover_etapa_success(client_user, seed_data):
    response = client_user.post(
        f"/api/tarefas/{seed_data['task_id']}/mover-etapa",
        json={"etapa_id": str(seed_data["etapa_started_id"])},
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["task_id"] == seed_data["task_id"]
    assert data["etapa_id"] == seed_data["etapa_started_id"]


def test_api_tarefas_arquivar_finalizadas_envelope(client_user):
    response = client_user.post("/api/tarefas/arquivar-finalizadas", json={})
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert "archived_count" in data
    assert isinstance(data["archived_task_ids"], list)
    assert "message" in data


def test_api_hub_sugestoes_responsavel(client_user, seed_data):
    response = client_user.get(
        "/api/tarefas/sugestoes-responsavel",
        query_string={"project": str(seed_data["project_id"])},
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert isinstance(data["users"], list)


def test_api_hub_sugestoes_responsavel_requires_scope(client_user):
    response = client_user.get("/api/tarefas/sugestoes-responsavel")
    assert response.status_code == 400
    _fail(response.get_json(), code="validation")


# ── CRUD de evento de calendário ──────────────────────────────────────────────


def test_api_calendar_event_create_local_only(client_user):
    response = client_user.post(
        "/api/calendarios/eventos",
        json={
            "title": "Evento Contrato",
            "starts_at": "2026-05-01T09:00",
            "ends_at": "2026-05-01T10:00",
        },
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["event"]["title"] == "Evento Contrato"
    # Sem conexão Google no seed => local_only.
    assert data["sync_outcome"] == "local_only"
    assert isinstance(data["sync_message"], str)


def test_api_calendar_event_create_invalid(client_user):
    response = client_user.post("/api/calendarios/eventos", json={"title": ""})
    assert response.status_code == 422
    _fail(response.get_json(), code="validation")


def test_api_calendar_event_edit_local_only(client_user, seed_data):
    response = client_user.post(
        f"/api/calendarios/eventos/{seed_data['calendar_event_id']}/editar",
        json={
            "title": "Evento Editado",
            "starts_at": "2026-05-01T09:00",
            "ends_at": "2026-05-01T10:00",
        },
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["event"]["title"] == "Evento Editado"
    assert data["sync_outcome"] == "local_only"


def test_api_calendar_event_edit_not_found(client_user):
    response = client_user.post(
        "/api/calendarios/eventos/999999/editar",
        json={
            "title": "X",
            "starts_at": "2026-05-01T09:00",
            "ends_at": "2026-05-01T10:00",
        },
    )
    assert response.status_code == 404
    _fail(response.get_json(), code="not_found")


def test_api_calendar_event_generate_meet_requires_connection(client_user, seed_data):
    response = client_user.post(
        f"/api/calendarios/eventos/{seed_data['calendar_event_id']}/gerar-meet"
    )
    assert response.status_code == 409
    _fail(response.get_json(), code="validation")


def test_api_calendar_event_delete_success(client_user, seed_data):
    response = client_user.post(
        f"/api/calendarios/eventos/{seed_data['calendar_event_id']}/excluir"
    )
    assert response.status_code == 200
    data = _ok(response.get_json())
    assert data["deleted"] is True


# ── Reuniões de etapa ─────────────────────────────────────────────────────────


def test_api_project_meeting_create_requires_google(client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/reunioes",
        json={
            "title": "Reunião Contrato",
            "starts_at": "2026-05-02T09:00",
            "ends_at": "2026-05-02T10:00",
        },
    )
    assert response.status_code == 400
    _fail(response.get_json(), code="validation")


def test_api_project_meeting_create_forbidden(client_outsider, seed_data):
    response = client_outsider.post(
        f"/api/projetos/{seed_data['project_id']}/reunioes",
        json={
            "title": "Reunião Contrato",
            "starts_at": "2026-05-02T09:00",
            "ends_at": "2026-05-02T10:00",
        },
    )
    assert response.status_code == 403
    _fail(response.get_json(), code="forbidden")


def test_api_project_meeting_edit_rejects_regular_stage(client_user, seed_data):
    # Etapa regular não é reunião Google editável => 400.
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_id']}/reuniao",
        json={
            "title": "X",
            "starts_at": "2026-05-02T09:00",
            "ends_at": "2026-05-02T10:00",
        },
    )
    assert response.status_code == 400
    _fail(response.get_json(), code="validation")


def test_api_project_meeting_edit_not_found(client_user):
    response = client_user.post(
        "/api/etapas/999999/reuniao",
        json={
            "title": "X",
            "starts_at": "2026-05-02T09:00",
            "ends_at": "2026-05-02T10:00",
        },
    )
    assert response.status_code == 404
    _fail(response.get_json(), code="not_found")
