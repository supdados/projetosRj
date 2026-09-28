"""P1-04: consulta e arquivamento devem atingir o mesmo conjunto filtrado."""

import pytest

from models import Project, Task, TaskAssignee, UserNotification, UserOrgao, db
from routes.tasks.hub import HUB_GROUPS_PER_PAGE


@pytest.fixture
def archive_pair(app, seed_data) -> tuple[int, int]:
    with app.app_context():
        target = db.session.get(Task, seed_data["task_id"])
        target.status = "finalizada"
        target.descricao = "Conferir termo exclusivo"
        target.tipo_pedido = "bug"
        target.prioridade = "alta"
        target.responsavel = None
        target.assignees = [TaskAssignee(user_id=seed_data["user_id"])]
        other = Task(
            descricao="Outro assunto",
            status="finalizada",
            project_id=seed_data["project_id"],
            created_by_id=seed_data["user_id"],
            prioridade="baixa",
            tipo_pedido="melhoria",
        )
        db.session.add(other)
        db.session.commit()
        return target.id, other.id


@pytest.mark.parametrize(
    "filters",
    [
        {"search": "termo exclusivo"},
        {"tipo": "bug"},
        {"prioridade": "alta"},
        {"responsavel": "Usuario Auditoria"},
        {"status": "nao_iniciada"},
    ],
)
def test_archive_matches_list_filters(app, client_user, archive_pair, filters) -> None:
    listed = client_user.get("/api/tarefas", query_string=filters)
    assert listed.status_code == 200
    expected = {
        task["id"]
        for group in listed.get_json()["data"]["groups"]
        for task in group["tasks"]
        if task["status"] == "finalizada"
    }
    response = client_user.post("/api/tarefas/arquivar-finalizadas", json=filters)
    assert response.status_code == 200
    assert {
        int(value) for value in response.get_json()["data"]["archived_task_ids"]
    } == expected
    with app.app_context():
        for task_id in archive_pair:
            assert db.session.get(Task, task_id).is_archived is (task_id in expected)


def test_board_applies_the_same_text_search(client_user, archive_pair) -> None:
    response = client_user.get("/api/tarefas/board?search=termo+exclusivo")
    assert response.status_code == 200
    tasks = [
        task["id"]
        for column in response.get_json()["data"]["columns"]
        for task in column["tasks"]
    ]
    assert tasks == [archive_pair[0]]


def test_archive_respects_effective_global_orgao(
    app, client_admin, seed_data, archive_pair
) -> None:
    with app.app_context():
        foreign = db.session.get(Task, seed_data["foreign_task_id"])
        foreign.status = "finalizada"
        db.session.commit()
    filters = {"orgao": str(seed_data["auditoria_orgao_id"])}
    listed = client_admin.get("/api/tarefas/board", query_string=filters).get_json()[
        "data"
    ]
    expected = {
        task["id"]
        for col in listed["columns"]
        for task in col["tasks"]
        if task["status"] == "finalizada"
    }
    response = client_admin.post("/api/tarefas/arquivar-finalizadas", json=filters)
    assert response.status_code == 200
    assert {
        int(value) for value in response.get_json()["data"]["archived_task_ids"]
    } == expected
    with app.app_context():
        assert not db.session.get(Task, seed_data["foreign_task_id"]).is_archived


def test_preview_counts_all_pages_without_archiving(
    app, client_user, seed_data
) -> None:
    with app.app_context():
        for index in range(HUB_GROUPS_PER_PAGE + 1):
            project = Project(
                titulo=f"Projeto lote {index}", orgao_id=seed_data["auditoria_orgao_id"]
            )
            project.tasks = [
                Task(
                    descricao="Lote paginado",
                    status="finalizada",
                    created_by_id=seed_data["user_id"],
                )
            ]
            db.session.add(project)
        db.session.commit()
        notifications_before = UserNotification.query.count()
    filters = {"search": "Lote paginado"}
    listing = client_user.get("/api/tarefas", query_string=filters).get_json()["data"]
    assert listing["pagination"]["total_pages"] == 2
    response = client_user.post(
        "/api/tarefas/arquivar-finalizadas", json={**filters, "preview": True}
    )
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["total"] == len(preview["task_ids"]) == HUB_GROUPS_PER_PAGE + 1
    with app.app_context():
        assert Task.query.filter_by(is_archived=True).count() == 0
        assert UserNotification.query.count() == notifications_before
    archived = client_user.post(
        "/api/tarefas/arquivar-finalizadas",
        json={**filters, "task_ids": preview["task_ids"]},
    )
    assert archived.status_code == 200
    assert archived.get_json()["data"]["archived_count"] == preview["total"]


def test_newly_finalized_task_is_not_added_after_confirmation(
    app, client_user, archive_pair
) -> None:
    target_id, other_id = archive_pair
    with app.app_context():
        db.session.get(Task, other_id).status = "em_andamento"
        db.session.commit()
    preview = client_user.post(
        "/api/tarefas/arquivar-finalizadas", json={"preview": True}
    ).get_json()["data"]
    assert preview["task_ids"] == [target_id]
    with app.app_context():
        db.session.get(Task, other_id).status = "finalizada"
        db.session.commit()
    result = client_user.post(
        "/api/tarefas/arquivar-finalizadas", json={"task_ids": preview["task_ids"]}
    )
    assert result.get_json()["data"]["archived_task_ids"] == [str(target_id)]
    with app.app_context():
        assert not db.session.get(Task, other_id).is_archived


@pytest.mark.parametrize("change", ["filter", "permission", "status"])
def test_commit_rechecks_eligibility_after_preview(
    app, client_user, seed_data, archive_pair, change
) -> None:
    filters = {"tipo": "bug"}
    preview = client_user.post(
        "/api/tarefas/arquivar-finalizadas", json={**filters, "preview": True}
    ).get_json()["data"]
    assert preview["total"] == 1
    with app.app_context():
        target = db.session.get(Task, archive_pair[0])
        if change == "filter":
            target.tipo_pedido = "melhoria"
        elif change == "permission":
            UserOrgao.query.filter_by(user_id=seed_data["user_id"]).delete()
        else:
            target.status = "em_andamento"
        db.session.commit()
    result = client_user.post(
        "/api/tarefas/arquivar-finalizadas",
        json={**filters, "task_ids": preview["task_ids"]},
    )
    assert result.status_code == 200
    assert result.get_json()["data"]["archived_count"] == 0
    with app.app_context():
        assert not db.session.get(Task, archive_pair[0]).is_archived


def test_submitted_ids_cannot_bypass_filters_or_access(
    client_user, seed_data, archive_pair
) -> None:
    response = client_user.post(
        "/api/tarefas/arquivar-finalizadas",
        json={
            "search": "termo exclusivo",
            "task_ids": [*archive_pair, seed_data["foreign_task_id"]],
        },
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["archived_task_ids"] == [str(archive_pair[0])]


def test_empty_confirmed_set_does_not_archive_everything(
    client_user, archive_pair
) -> None:
    result = client_user.post(
        "/api/tarefas/arquivar-finalizadas", json={"task_ids": []}
    )
    assert result.status_code == 200
    assert result.get_json()["data"]["archived_count"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"preview": "true"},
        {"task_ids": None},
        {"task_ids": "1"},
        {"task_ids": [True]},
        {"task_ids": [-1]},
    ],
)
def test_invalid_confirmation_is_rejected(
    app, client_user, archive_pair, payload
) -> None:
    response = client_user.post("/api/tarefas/arquivar-finalizadas", json=payload)
    assert response.status_code == 422
    with app.app_context():
        assert Task.query.filter_by(is_archived=True).count() == 0


def test_malformed_filter_body_cannot_fall_back_to_archive_all(
    app, client_user, archive_pair
) -> None:
    response = client_user.post(
        "/api/tarefas/arquivar-finalizadas",
        data='{"search":',
        content_type="application/json",
    )
    assert response.status_code == 422
    with app.app_context():
        assert Task.query.filter_by(is_archived=True).count() == 0
