"""Snapshot das CHAVES de cada payload de tarefa servido pela API.

O front reconcilia os cards vindos de rotas diferentes (criação, hub, quick-add
de etapa, dashboard, drawer). Estes testes fixam o shape campo a campo para que a
unificação dos serializadores em ``serialize_task_card`` (sprint 3.2) não some
com nenhuma chave nem introduza chave nova sem intenção.
"""

TASK_CARD_KEYS = {
    "id",
    "descricao",
    "status",
    "responsavel",
    "assignees",
    "prioridade",
    "tipo_pedido",
    "ordem",
    "project_id",
    "project_titulo",
    "etapa_id",
    "created_by_id",
    "created_at",
    "is_archived",
    "archived_at",
    "comments_count",
    "anexos_count",
    "permissions",
}

CONTEXT_LABEL_KEYS = {"etapa_descricao", "project_orgao_sigla"}


def _data(response):
    payload = response.get_json()
    assert payload["ok"] is True, payload
    return payload["data"]


def test_serialize_task_card_shape_base(app, seed_data):
    from models import Task, db
    from routes.api.serializers import serialize_task_card

    with app.app_context():
        card = serialize_task_card(db.session.get(Task, seed_data["task_id"]))

    assert set(card) == TASK_CARD_KEYS
    assert set(card["permissions"]) == {"can_finalize"}


def test_serialize_task_card_shape_com_parametros(app, seed_data):
    from models import Task, db
    from routes.api.serializers import serialize_task_card

    with app.app_context():
        card = serialize_task_card(
            db.session.get(Task, seed_data["task_id"]),
            with_manage_permissions=True,
            with_context_labels=True,
        )

    assert set(card) == TASK_CARD_KEYS | CONTEXT_LABEL_KEYS
    assert set(card["permissions"]) == {"can_finalize", "can_delete", "is_author"}


def test_context_labels_de_tarefa_avulsa_usam_fallbacks(app, seed_data):
    from models import Task, db
    from routes.api.serializers import serialize_task_card

    with app.app_context():
        card = serialize_task_card(
            db.session.get(Task, seed_data["orphan_task_id"]),
            with_context_labels=True,
        )

    assert card["project_titulo"] == "Sem projeto"
    assert card["etapa_descricao"] == ""
    assert card["project_orgao_sigla"] == ""


def test_criar_tarefa_devolve_card_com_contexto_e_permissoes(client_user, seed_data):
    response = client_user.post(
        "/api/tarefas",
        json={
            "project_id": seed_data["project_id"],
            "etapa_id": seed_data["etapa_id"],
            "descricao": "Tarefa para snapshot",
        },
    )

    assert response.status_code == 200
    card = _data(response)["task"]
    assert set(card) == TASK_CARD_KEYS | CONTEXT_LABEL_KEYS
    assert set(card["permissions"]) == {"can_finalize", "can_delete", "is_author"}
    assert card["project_titulo"] == "Projeto Auditoria"
    assert card["etapa_descricao"] == "Etapa Planejada"


def test_quick_add_de_etapa_devolve_card_com_permissoes(client_user, seed_data):
    client_user.post(
        "/api/tarefas",
        json={
            "project_id": seed_data["project_id"],
            "etapa_id": seed_data["etapa_id"],
            "descricao": "Tarefa da etapa",
        },
    )
    response = client_user.get(
        f"/api/projetos/{seed_data['project_id']}"
        f"/etapas/{seed_data['etapa_id']}/tarefas"
    )

    assert response.status_code == 200
    tarefas = _data(response)["tarefas"]
    assert tarefas, "seed deveria ter ao menos uma tarefa na etapa"
    for tarefa in tarefas:
        assert set(tarefa) == TASK_CARD_KEYS
        assert set(tarefa["permissions"]) == {"can_finalize", "can_delete", "is_author"}


def test_hub_de_tarefas_devolve_card_com_rotulos_de_etapa(client_user, seed_data):
    response = client_user.get("/api/tarefas")

    assert response.status_code == 200
    grupos = _data(response)["groups"]
    assert grupos, "seed deveria produzir ao menos um grupo"
    for grupo in grupos:
        for tarefa in grupo["tasks"]:
            assert set(tarefa) == TASK_CARD_KEYS | {
                "etapa_titulo",
                "etapa_display_id",
                "is_first_of_stage",
            }


def test_dashboard_recentes_usam_o_card_canonico(client_user, seed_data):
    response = client_user.get("/api/dashboard")

    assert response.status_code == 200
    recentes = _data(response)["recent_tasks"]
    assert recentes, "seed deveria produzir tarefas recentes"
    for tarefa in recentes:
        assert set(tarefa) == TASK_CARD_KEYS


def test_drawer_detail_soma_contexto_comentarios_e_anexos(client_user, seed_data):
    response = client_user.get(f"/api/tarefas/{seed_data['task_id']}/detalhe")

    assert response.status_code == 200
    data = _data(response)
    assert set(data["task"]) == TASK_CARD_KEYS
    assert set(data["detail"]) == TASK_CARD_KEYS | {
        "etapa",
        "project",
        "comentarios",
        "anexos",
    }
    assert set(data["detail"]["permissions"]) == {
        "can_edit",
        "can_finalize",
        "can_delete",
    }
