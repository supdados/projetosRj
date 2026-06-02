"""Testes de contrato dos endpoints /api ADITIVOS da SPA (envelope canônico).

Cobrem os endpoints novos da fase atual e os campos novos de serializer:

    - ``DELETE /api/projetos/<id>``        — exclusão REAL (sucesso + 403 fora do
      escopo + 404 + 401).
    - ``GET    /api/notificacoes``         — lista visível + ``unread_count``.
    - ``POST   /api/notificacoes/marcar-lidas`` — marca lidas (envelope).
    - ``GET    /api/orgaos/escopo``        — árvore aninhada do escopo do usuário.
    - ``serialize_task_card.project_titulo`` e
      ``serialize_template_row.silhouette`` (campos novos de contrato).
    - ``serialize_project_card.delivery_type`` na lista de projetos.

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo,
``client_user`` não-admin e ``client_admin``).
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
# DELETE /api/projetos/<id>
# ---------------------------------------------------------------------------


def test_delete_project_returns_ok_and_persists(app, client_user, seed_data):
    from models import Project, db

    project_id = seed_data["project_id"]
    response = client_user.delete(f"/api/projetos/{project_id}")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data == {"deleted": True, "id": project_id}

    with app.app_context():
        assert db.session.get(Project, project_id) is None  # removido de verdade


def test_delete_project_registra_historico(app, client_user, seed_data):
    # A exclusão registra um evento "delete" no histórico antes de remover (a
    # cascata mantém o histórico? não — o histórico do projeto cai junto). Aqui
    # validamos apenas que a chamada de log não quebra a transação de delete.
    project_id = seed_data["project_id"]
    response = client_user.delete(f"/api/projetos/{project_id}")
    assert response.status_code == 200


def test_delete_project_returns_403_fora_do_escopo(app, client_user, seed_data):
    from models import Project, db

    foreign_id = seed_data["foreign_project_id"]
    response = client_user.delete(f"/api/projetos/{foreign_id}")

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")
    with app.app_context():
        assert db.session.get(Project, foreign_id) is not None  # NÃO foi apagado


def test_delete_project_returns_404_inexistente(client_user):
    response = client_user.delete("/api/projetos/999999")
    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_delete_project_returns_401_anonimo(client, seed_data):
    response = client.delete(f"/api/projetos/{seed_data['project_id']}")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


# ---------------------------------------------------------------------------
# GET /api/notificacoes + POST /api/notificacoes/marcar-lidas
# ---------------------------------------------------------------------------


def _add_notification(app, recipient_id, *, is_read=False, target_url="/tarefas"):
    from models import UserNotification, db

    with app.app_context():
        notif = UserNotification(
            recipient_user_id=recipient_id,
            event_type="task_assigned",
            title="Nova tarefa",
            message="Você foi designado",
            target_url=target_url,
            is_read=is_read,
        )
        db.session.add(notif)
        db.session.commit()
        return notif.id


def test_notificacoes_list_returns_items_and_unread_count(app, client_user, seed_data):
    _add_notification(app, seed_data["user_id"], is_read=False)
    _add_notification(app, seed_data["user_id"], is_read=True)

    response = client_user.get("/api/notificacoes")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["items"], list)
    assert data["unread_count"] == 1
    item = data["items"][0]
    assert set(item.keys()) == {
        "id",
        "event_type",
        "title",
        "message",
        "created_at",
        "actor_name",
        "is_unread",
        "target_url",
    }


def test_notificacoes_list_nao_marca_como_lida(app, client_user, seed_data):
    # A rota de leitura NÃO deve mutar is_read (diferente do dropdown legado).
    _add_notification(app, seed_data["user_id"], is_read=False)
    client_user.get("/api/notificacoes")

    data = _assert_ok_envelope(client_user.get("/api/notificacoes").get_json())
    assert data["unread_count"] == 1


def test_notificacoes_marcar_lidas_zera_unread(app, client_user, seed_data):
    _add_notification(app, seed_data["user_id"], is_read=False)
    _add_notification(app, seed_data["user_id"], is_read=False)

    response = client_user.post("/api/notificacoes/marcar-lidas")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["marked"] == 2
    assert data["unread_count"] == 0

    after = _assert_ok_envelope(client_user.get("/api/notificacoes").get_json())
    assert after["unread_count"] == 0


def test_notificacoes_list_returns_401_anonimo(client):
    response = client.get("/api/notificacoes")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


# ---------------------------------------------------------------------------
# GET /api/orgaos/escopo
# ---------------------------------------------------------------------------


def test_orgaos_escopo_returns_nested_tree(client_user):
    response = client_user.get("/api/orgaos/escopo")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["tree"], list)
    # Cada nó traz children + flags de escopo do usuário.
    for node in data["tree"]:
        assert "children" in node
        assert "is_user_orgao" in node
        assert "is_user_ancestor" in node
        assert "tipo" in node


def test_orgaos_escopo_admin_ve_arvore(client_admin):
    response = client_admin.get("/api/orgaos/escopo")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["tree"], list)
    assert data["tree"]  # admin vê ao menos a raiz


def test_orgaos_escopo_returns_401_anonimo(client):
    response = client.get("/api/orgaos/escopo")
    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


# ---------------------------------------------------------------------------
# Campos novos de serializer
# ---------------------------------------------------------------------------


def test_task_card_inclui_project_titulo(app, seed_data):
    from models import Project, Task, db

    from routes.api.serializers import serialize_task_card

    with app.app_context():
        task = db.session.get(Task, seed_data["task_id"])
        project = db.session.get(Project, task.project_id)
        card = serialize_task_card(task)
        assert card["project_titulo"] == project.titulo


def test_template_row_inclui_silhouette():
    from routes.api.serializers import serialize_template_row

    row = {
        "id": 1,
        "name": "Modelo",
        "description": "",
        "initials": "MO",
        "stage_count": 2,
        "total_duration": 10,
        "silhouette": [(28, 7), (12, 3)],
        "usage_count": 0,
        "updated_at": None,
        "updated_relative": "agora",
        "editor_name": "Ana",
        "is_new": False,
    }
    serialized = serialize_template_row(row)
    # Pares [altura, duracao] como listas JSON-safe.
    assert serialized["silhouette"] == [[28, 7], [12, 3]]


def test_project_card_inclui_delivery_type(app, seed_data):
    from models import Project, db

    from routes.api.serializers import serialize_project_card

    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        card = serialize_project_card(project)
        assert "delivery_type" in card


def test_lista_projetos_inclui_delivery_type(client_user):
    response = client_user.get("/api/projetos")
    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    for project in data["projetos"]:
        assert "delivery_type" in project
