"""P2-13: busca e resumo usam os responsáveis atuais sem perder legado válido."""

import pytest

from models import Task, TaskAssignee, User, db


def task_results(client, endpoint: str, term: str) -> list[dict[str, object]]:
    response = client.get(endpoint, query_string={"q": term, "limit": "all"})
    assert response.status_code == 200
    payload = response.get_json()
    if endpoint == "/api/busca":
        payload = payload["data"]
    return payload["results"]["tasks"]


@pytest.mark.parametrize("endpoint", ["/api/busca", "/api/busca-global"])
def test_created_task_is_found_by_assignee_and_updates_on_replacement(
    app, client_user, seed_data, endpoint
) -> None:
    created = client_user.post(
        "/api/tarefas",
        json={
            "project": seed_data["project_id"],
            "descricao": "Tarefa NN exclusiva",
            "assignee_ids": [seed_data["editable_user_id"]],
        },
    )
    assert created.status_code == 200
    task_id = created.get_json()["data"]["task"]["id"]
    rows = task_results(client_user, endpoint, "Usuario Editavel")
    assert any(row["title"] == "Tarefa NN exclusiva" for row in rows)
    row = next(row for row in rows if row["title"] == "Tarefa NN exclusiva")
    assert "Usuario Editavel" in row["meta"]
    assert row["match_field"] == "responsavel"
    replaced = client_user.post(
        f"/api/tarefas/{task_id}/responsaveis",
        json={"user_ids": [seed_data["user_id"]]},
    )
    assert replaced.status_code == 200
    assert all(
        row["title"] != "Tarefa NN exclusiva"
        for row in task_results(client_user, endpoint, "Usuario Editavel")
    )
    assert any(
        row["title"] == "Tarefa NN exclusiva"
        for row in task_results(client_user, endpoint, "Usuario Auditoria")
    )


@pytest.mark.parametrize("endpoint", ["/api/busca", "/api/busca-global"])
@pytest.mark.parametrize("clear_all", [False, True])
def test_explicit_assignment_clears_previous_legacy_names(
    app, client_user, seed_data, endpoint, clear_all
) -> None:
    with app.app_context():
        task = db.session.get(Task, seed_data["task_id"])
        task.responsavel = "Pessoa Legada Antiga"
        db.session.commit()
    response = client_user.post(
        f"/api/tarefas/{seed_data['task_id']}/responsaveis",
        json={"user_ids": [] if clear_all else [seed_data["editable_user_id"]]},
    )
    assert response.status_code == 200
    assert task_results(client_user, endpoint, "Pessoa Legada Antiga") == []
    with app.app_context():
        assert db.session.get(Task, seed_data["task_id"]).responsavel is None


def test_global_search_keeps_authorization_scope(app, client_user, seed_data) -> None:
    with app.app_context():
        foreign = db.session.get(Task, seed_data["foreign_task_id"])
        foreign.assignees = [TaskAssignee(user_id=seed_data["editable_user_id"])]
        db.session.commit()
    assert task_results(client_user, "/api/busca", "Usuario Editavel") == []


@pytest.mark.parametrize("endpoint", ["/api/busca", "/api/busca-global"])
def test_unmatched_legacy_names_remain_searchable_with_nn(
    app, client_user, seed_data, endpoint
) -> None:
    with app.app_context():
        task = db.session.get(Task, seed_data["task_id"])
        task.responsavel = "Equipe Externa Preservada"
        task.assignees = [TaskAssignee(user_id=seed_data["editable_user_id"])]
        db.session.commit()
    for term in ("Equipe Externa Preservada", "Usuario Editavel"):
        rows = task_results(client_user, endpoint, term)
        assert len(rows) == 1
        assert "Equipe Externa Preservada" in rows[0]["meta"]
        assert "Usuario Editavel" in rows[0]["meta"]


def test_paginated_search_does_not_duplicate_task_with_two_matching_assignees(
    app, client_user, seed_data
) -> None:
    with app.app_context():
        db.session.get(User, seed_data["user_id"]).name = "Zeta Pessoa Um"
        db.session.get(User, seed_data["editable_user_id"]).name = "Zeta Pessoa Dois"
        task = db.session.get(Task, seed_data["task_id"])
        task.responsavel = None
        task.assignees = [
            TaskAssignee(user_id=seed_data[key])
            for key in ("user_id", "editable_user_id")
        ]
        db.session.commit()
    response = client_user.get(
        "/api/busca", query_string={"q": "Zeta Pessoa", "page": 1, "types": "tasks"}
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["counts"]["tasks"] == 1
    assert len(payload["results"]["tasks"]) == 1
    assert "Zeta Pessoa Dois, Zeta Pessoa Um" in payload["results"]["tasks"][0]["meta"]


def test_creation_with_legacy_input_keeps_the_provided_responsavel(
    app, client_user, seed_data
) -> None:
    response = client_user.post(
        "/api/tarefas",
        json={
            "project": seed_data["project_id"],
            "descricao": "Entrada legada explícita",
            "responsavel": "Usuario Auditoria",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        assert (
            db.session.get(Task, response.get_json()["data"]["task"]["id"]).responsavel
            == "Usuario Auditoria"
        )
