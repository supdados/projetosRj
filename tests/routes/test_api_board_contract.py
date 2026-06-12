"""Testes de contrato dos endpoints JSON do Kanban de Tarefas (Fase 5b-1).

Afirmam o envelope canônico ``{"ok": true, "data": ...}`` /
``{"ok": false, "error": {"code", "message"}}`` de:

    - ``GET  /api/tarefas/board``           — 5 colunas por status + cards;
    - ``POST /api/tarefas/<id>/status``     — mudança de status (autoritativa);
    - ``POST /api/tarefas/board/reordenar`` — reordenação (e status entre colunas).

Cobrem os guards/validações exigidos: 200 (sucesso), 401 (sem sessão), 403
(finalizar sem permissão — decisão AUTORITATIVA server-side via
``_can_transition_task_to_status``), 422 (status inválido) e 404 (tarefa
inexistente). Reutilizam as fixtures de ``tests/conftest.py`` (``client`` anônimo,
``client_user`` = autor da tarefa, ``client_editable`` = mesmo órgão mas NÃO
autor) e o banco semeado. Sem mocks de rede.
"""

from __future__ import annotations

from typing import Any

from routes.api.board import _sort_cards_by_priority
from routes.tasks.permissions import FINALIZE_DENIED_MESSAGE
from routes.tasks.constants import TASK_STATUS_ORDER


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
# Ordenação por prioridade dentro da coluna (board já é agrupado por status)
# ---------------------------------------------------------------------------


def test_sort_cards_by_priority_orders_urgente_first():
    cards = [
        {"id": 1, "prioridade": "baixa"},
        {"id": 2, "prioridade": "urgente"},
        {"id": 3, "prioridade": "media"},
        {"id": 4, "prioridade": "alta"},
    ]
    assert [c["id"] for c in _sort_cards_by_priority(cards)] == [2, 4, 3, 1]


def test_sort_cards_by_priority_is_stable_for_manual_order():
    # Mesma prioridade preserva a ordem de entrada (Task.ordem do banco/DnD).
    cards = [
        {"id": 7, "prioridade": "alta"},
        {"id": 3, "prioridade": "alta"},
        {"id": 5, "prioridade": "alta"},
    ]
    assert [c["id"] for c in _sort_cards_by_priority(cards)] == [7, 3, 5]


def test_sort_cards_by_priority_puts_missing_priority_last():
    cards = [
        {"id": 1, "prioridade": None},
        {"id": 2, "prioridade": "baixa"},
    ]
    assert [c["id"] for c in _sort_cards_by_priority(cards)] == [2, 1]


# ---------------------------------------------------------------------------
# GET /api/tarefas/board
# ---------------------------------------------------------------------------


def test_api_board_returns_five_columns_in_canonical_order(client_user, seed_data):
    response = client_user.get("/api/tarefas/board")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    columns = data["columns"]
    assert [column["status"] for column in columns] == list(TASK_STATUS_ORDER)
    assert all("label" in column and "tasks" in column for column in columns)
    assert isinstance(data["total"], int)
    assert "selected_orgao" in data["filters"]


def test_api_board_card_exposes_can_finalize_and_no_secrets(client_user, seed_data):
    response = client_user.get("/api/tarefas/board")

    data = _assert_ok_envelope(response.get_json())
    seeded = {
        card["id"]: card for column in data["columns"] for card in column["tasks"]
    }
    card = seeded[seed_data["task_id"]]
    assert card["permissions"]["can_finalize"] is True  # autor é o usuário logado
    assert "password_hash" not in card


def test_api_board_card_exposes_comments_and_anexos_counts(app, client_user, seed_data):
    # Os contadores do rodapé do card (balão/clipe) devem refletir o banco.
    from extensions import db
    from models.task import TaskAnexo, TaskComment

    with app.app_context():
        db.session.add(
            TaskComment(
                content="Comentário de contagem",
                user_id=seed_data["user_id"],
                task_id=seed_data["task_id"],
            )
        )
        db.session.add(
            TaskAnexo(
                task_id=seed_data["task_id"],
                filename="evidencia.pdf",
                stored_filename="evidencia-stored.pdf",
                uploaded_by_id=seed_data["user_id"],
            )
        )
        db.session.commit()

    response = client_user.get("/api/tarefas/board")

    data = _assert_ok_envelope(response.get_json())
    seeded = {
        card["id"]: card for column in data["columns"] for card in column["tasks"]
    }
    card = seeded[seed_data["task_id"]]
    # Os contadores devem refletir o banco — asserimos contra a contagem REAL,
    # não um literal: o seed já anexa um "Comentario inicial" a esta task
    # (TaskItemComment é alias de TaskComment), então o total de comentários é 2
    # (seed + o adicionado aqui), enquanto o anexo do seed vai para `orphan_task`
    # e não conta aqui. Comparar com a contagem do banco pega dupla-contagem/drift
    # sem depender do estado exato do seed.
    with app.app_context():
        expected_comments = TaskComment.query.filter_by(
            task_id=seed_data["task_id"]
        ).count()
        expected_anexos = TaskAnexo.query.filter_by(
            task_id=seed_data["task_id"]
        ).count()
    assert card["comments_count"] == expected_comments
    assert card["anexos_count"] == expected_anexos


def test_api_board_requires_session(client):
    response = client.get("/api/tarefas/board")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


# ---------------------------------------------------------------------------
# POST /api/tarefas/<id>/status
# ---------------------------------------------------------------------------


def test_api_status_changes_status_and_returns_card(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/status", json={"status": "para_validacao"}
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["task"]["id"] == task_id
    assert data["task"]["status"] == "para_validacao"


def test_api_status_author_can_finalize(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/status", json={"status": "finalizada"}
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["task"]["status"] == "finalizada"


def test_api_status_requires_session(client, seed_data):
    task_id = seed_data["task_id"]
    response = client.post(
        f"/api/tarefas/{task_id}/status", json={"status": "em_andamento"}
    )

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_status_invalid_status_is_422(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/status", json={"status": "inexistente"}
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_status_unknown_task_is_404(client_user):
    response = client_user.post(
        "/api/tarefas/999999/status", json={"status": "em_andamento"}
    )

    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_api_status_finalize_without_permission_is_403_authoritative(
    client_editable, seed_data
):
    """Usuário do mesmo órgão (pode VER) mas NÃO autor: servidor recusa finalizar.

    A regra de UX no cliente é só dica; a decisão é server-side via
    ``_can_transition_task_to_status``. O backend devolve 403 ``forbidden`` com
    ``FINALIZE_DENIED_MESSAGE`` mesmo que o cliente tente o move.
    """
    task_id = seed_data["task_id"]
    response = client_editable.post(
        f"/api/tarefas/{task_id}/status", json={"status": "finalizada"}
    )

    assert response.status_code == 403
    payload = response.get_json()
    _assert_fail_envelope(payload, code="forbidden")
    assert payload["error"]["message"] == FINALIZE_DENIED_MESSAGE


def test_api_status_non_finalize_move_allowed_for_viewer(client_editable, seed_data):
    """Transições que NÃO são para 'finalizada' são permitidas a qualquer viewer."""
    task_id = seed_data["task_id"]
    response = client_editable.post(
        f"/api/tarefas/{task_id}/status", json={"status": "em_andamento"}
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["task"]["status"] == "em_andamento"


# ---------------------------------------------------------------------------
# POST /api/tarefas/board/reordenar
# ---------------------------------------------------------------------------


def test_api_reorder_persists_order_within_column(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        "/api/tarefas/board/reordenar",
        json={"columns": [{"status": "nao_iniciada", "task_ids": [task_id]}]},
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    column = data["columns"][0]
    assert column["status"] == "nao_iniciada"
    assert [card["id"] for card in column["tasks"]] == [task_id]


def test_api_reorder_requires_session(client, seed_data):
    response = client.post(
        "/api/tarefas/board/reordenar",
        json={
            "columns": [{"status": "nao_iniciada", "task_ids": [seed_data["task_id"]]}]
        },
    )

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_reorder_invalid_column_status_is_422(client_user, seed_data):
    response = client_user.post(
        "/api/tarefas/board/reordenar",
        json={
            "columns": [{"status": "inexistente", "task_ids": [seed_data["task_id"]]}]
        },
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_reorder_unknown_task_is_404(client_user):
    response = client_user.post(
        "/api/tarefas/board/reordenar",
        json={"columns": [{"status": "nao_iniciada", "task_ids": [999999]}]},
    )

    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_api_reorder_cross_column_finalize_denied_is_403(client_editable, seed_data):
    """Mover (via reorder) um card para a coluna 'finalizada' sem permissão => 403."""
    task_id = seed_data["task_id"]
    response = client_editable.post(
        "/api/tarefas/board/reordenar",
        json={"columns": [{"status": "finalizada", "task_ids": [task_id]}]},
    )

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")
