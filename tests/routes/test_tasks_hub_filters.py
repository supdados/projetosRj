from models import Task, db
from time_utils import utc_now


def _hub_descriptions(client, path):
    """Extrai as descricoes das tarefas do envelope JSON de ``/api/tarefas``.

    Apos o cut-over o hub serve a shell da SPA; o conteudo filtrado vem do
    endpoint JSON (mesma fonte ``build_task_hub_context``). Achatamos os grupos
    em uma lista de descricoes para validar a logica de filtragem.
    """
    payload = client.get(path).get_json()
    assert payload["ok"] is True
    descriptions = []
    for group in payload["data"]["groups"]:
        descriptions.extend(task["descricao"] for task in group["tasks"])
    return descriptions


def test_tasks_hub_filters_by_priority_type_status_and_responsavel(
    app, client_user, seed_data
):
    with app.app_context():
        matching_task = Task(
            descricao="Tarefa filtro alvo",
            status="em_andamento",
            responsavel="Usuario Editavel",
            prioridade="alta",
            tipo_pedido="bug",
            ordem=10,
            project_id=seed_data["project_id"],
            created_by_id=seed_data["user_id"],
        )
        other_task = Task(
            descricao="Tarefa fora do filtro",
            status="nao_iniciada",
            responsavel="Usuario Auditoria",
            prioridade="baixa",
            tipo_pedido="melhoria",
            ordem=11,
            project_id=seed_data["project_id"],
            created_by_id=seed_data["user_id"],
        )
        db.session.add_all([matching_task, other_task])
        db.session.commit()

    descriptions = _hub_descriptions(
        client_user,
        "/api/tarefas?prioridade=alta&tipo=bug&status=em_andamento&responsavel=Usuario+Editavel",
    )
    assert "Tarefa filtro alvo" in descriptions
    assert "Tarefa fora do filtro" not in descriptions
    assert "Item Auditoria" not in descriptions


def test_finalized_listing_filters_by_priority_type_status_and_responsavel(
    app, client_user, seed_data
):
    with app.app_context():
        archived_match = Task(
            descricao="Arquivada filtro alvo",
            status="finalizada",
            responsavel="Usuario Editavel",
            prioridade="urgente",
            tipo_pedido="bug",
            ordem=20,
            project_id=seed_data["project_id"],
            created_by_id=seed_data["user_id"],
            is_archived=True,
            archived_at=utc_now(),
        )
        archived_other = Task(
            descricao="Arquivada fora do filtro",
            status="finalizada",
            responsavel="Usuario Auditoria",
            prioridade="media",
            tipo_pedido="melhoria",
            ordem=21,
            project_id=seed_data["project_id"],
            created_by_id=seed_data["user_id"],
            is_archived=True,
            archived_at=utc_now(),
        )
        db.session.add_all([archived_match, archived_other])
        db.session.commit()

    descriptions = _hub_descriptions(
        client_user,
        "/api/tarefas?modo=arquivadas&prioridade=urgente&tipo=bug&status=finalizada&responsavel=Usuario+Editavel",
    )
    assert "Arquivada filtro alvo" in descriptions
    assert "Arquivada fora do filtro" not in descriptions


def test_tasks_hub_redirects_when_non_admin_forces_foreign_orgao(
    client_user, seed_data
):
    response = client_user.get(
        "/tarefas",
        query_string={
            "orgao": str(seed_data["vpd_orgao_id"]),
            "status": "em_andamento",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tarefas?status=em_andamento")


def test_tasks_hub_project_filter_respects_selected_orgao_for_admin(
    client_admin, seed_data
):
    payload = client_admin.get(
        "/api/tarefas", query_string={"orgao": str(seed_data["vpd_orgao_id"])}
    ).get_json()
    assert payload["ok"] is True

    option_values = {opt["value"] for opt in payload["data"]["project_options"]}
    assert str(seed_data["foreign_project_id"]) in option_values
    assert str(seed_data["project_id"]) not in option_values
