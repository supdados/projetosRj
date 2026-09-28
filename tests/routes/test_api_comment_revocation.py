"""P1-02: a autoria permite mutação própria, mas não leitura após revogação."""

import pytest

from models import TaskComment, UserOrgao, db


@pytest.mark.parametrize("operation", ["edit", "delete"])
def test_own_comment_mutation_does_not_disclose_revoked_task(
    app, client_user, client_admin, seed_data, operation
) -> None:
    task_id = seed_data["task_id"]
    comment_id = seed_data["comment_id"]
    assert client_user.get(f"/api/tarefas/{task_id}/detalhe").status_code == 200
    with app.app_context():
        UserOrgao.query.filter_by(user_id=seed_data["user_id"]).delete()
        db.session.commit()
    private = client_admin.post(
        f"/api/tarefas/{task_id}/comentarios",
        json={"content": "Discussão posterior à revogação"},
    )
    assert private.status_code == 200
    private_id = private.get_json()["data"]["comment"]["id"]
    assert client_user.get(f"/api/tarefas/{task_id}/detalhe").status_code == 404

    path = f"/api/comentarios/{comment_id}"
    if operation == "delete":
        path += "/delete"
    response = client_user.post(path, json={"content": "Meu texto corrigido"})
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["comentarios"] == []
    assert "Discussão posterior" not in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(TaskComment, private_id) is not None
        own = db.session.get(TaskComment, comment_id)
        if operation == "delete":
            assert own is None
            assert payload["comment_id"] == comment_id
        else:
            assert own.content == "Meu texto corrigido"
            assert payload["comment"]["id"] == comment_id


def test_revoked_author_cannot_resolve_current_project_people(
    app, client_user, seed_data
) -> None:
    with app.app_context():
        UserOrgao.query.filter_by(user_id=seed_data["user_id"]).delete()
        db.session.commit()
    response = client_user.post(
        f"/api/comentarios/{seed_data['comment_id']}",
        json={"content": "Texto próprio com @Usuario Editavel"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["comment"]["mentions"] == []
