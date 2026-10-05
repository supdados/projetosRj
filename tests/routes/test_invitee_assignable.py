"""Convidado do projeto (ProjectMember ativo) pode ser responsável e mencionado.

Regressão: a lista de atribuíveis considerava só o órgão do projeto, então quem
de fora da equipe recebia convite via o projeto mas não aparecia nos pickers e
era descartado em silêncio nas escritas.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models import ProjectMember, Task, TaskComment, db
from services.authorization import PAPEL_EDITOR, PAPEL_LEITOR
from time_utils import utc_now


def _convidar(
    app, seed_data, user_key: str, papel: str = PAPEL_EDITOR, **extra
) -> None:
    with app.app_context():
        db.session.add(
            ProjectMember(
                project_id=extra.pop("project_id", seed_data["project_id"]),
                user_id=seed_data[user_key],
                papel=papel,
                granted_by_id=seed_data["user_id"],
                **extra,
            )
        )
        db.session.commit()


def _nomes_sugeridos(client, seed_data) -> tuple[set[str], set[str]]:
    hub = client.get(
        f"/api/tarefas/sugestoes-responsavel?project={seed_data['project_id']}"
    )
    drawer = client.get(f"/api/tarefas/{seed_data['task_id']}/sugestoes-responsavel")
    assert hub.status_code == 200 and drawer.status_code == 200
    return (
        {u["name"] for u in hub.get_json()["data"]["users"]},
        {u["name"] for u in drawer.get_json()["data"]["users"]},
    )


def test_convidados_leitor_e_editor_aparecem_nas_sugestoes(app, client_user, seed_data):
    _convidar(app, seed_data, "outsider_id", PAPEL_EDITOR)
    _convidar(app, seed_data, "deletable_user_id", PAPEL_LEITOR)

    hub, drawer = _nomes_sugeridos(client_user, seed_data)

    assert {"Usuario VPD", "Usuario Deletavel"} <= hub
    assert {"Usuario VPD", "Usuario Deletavel"} <= drawer


def _convite_sem_efeito(cenario: str, seed_data) -> dict:
    if cenario == "revogado":
        return {"revoked_at": utc_now()}
    if cenario == "expirado":
        return {"expires_at": utc_now() - timedelta(days=1)}
    return {"project_id": seed_data["project_complete_id"]}


@pytest.mark.parametrize("cenario", ["revogado", "expirado", "outro_projeto"])
def test_convite_inativo_ou_de_outro_projeto_nao_e_candidato(
    app, client_user, seed_data, cenario
):
    _convidar(app, seed_data, "outsider_id", **_convite_sem_efeito(cenario, seed_data))

    hub, drawer = _nomes_sugeridos(client_user, seed_data)

    assert "Usuario VPD" not in hub
    assert "Usuario VPD" not in drawer


def test_responsaveis_aceita_e_mantem_convidado_no_resave(app, client_user, seed_data):
    _convidar(app, seed_data, "outsider_id")
    path = f"/api/tarefas/{seed_data['task_id']}/responsaveis"

    client_user.post(path, json={"user_ids": [seed_data["outsider_id"]]})
    resave = client_user.post(
        path, json={"user_ids": [seed_data["outsider_id"], seed_data["user_id"]]}
    )

    assert resave.status_code == 200
    with app.app_context():
        task = db.session.get(Task, seed_data["task_id"])
        assigned = {a.user_id for a in task.assignees}
    assert assigned == {seed_data["outsider_id"], seed_data["user_id"]}


def test_criar_tarefa_aceita_convidado_por_id_e_por_nome(app, client_user, seed_data):
    _convidar(app, seed_data, "outsider_id")

    por_id = client_user.post(
        "/api/tarefas",
        json={
            "project": seed_data["project_id"],
            "descricao": "Tarefa do convidado",
            "assignee_ids": [seed_data["outsider_id"]],
        },
    )
    por_nome = client_user.post(
        "/api/tarefas",
        json={
            "project": seed_data["project_id"],
            "descricao": "Tarefa do convidado por nome",
            "responsavel": "Usuario VPD",
        },
    )

    assert por_id.status_code == 200
    assert por_nome.status_code == 200
    with app.app_context():
        task = db.session.get(Task, por_id.get_json()["data"]["task"]["id"])
        assert [a.user_id for a in task.assignees] == [seed_data["outsider_id"]]


def test_criar_tarefa_ainda_recusa_quem_nao_tem_convite(client_user, seed_data):
    response = client_user.post(
        "/api/tarefas",
        json={
            "project": seed_data["project_id"],
            "descricao": "Tarefa sem convite",
            "responsavel": "Usuario VPD",
        },
    )

    assert response.status_code == 422


def test_mencao_a_convidado_e_resolvida(app, client_user, seed_data):
    _convidar(app, seed_data, "outsider_id", PAPEL_LEITOR)

    response = client_user.post(
        f"/api/tarefas/{seed_data['task_id']}/comentarios",
        json={"content": "Pode revisar, @Usuario VPD?"},
    )

    assert response.status_code == 200
    comment_id = response.get_json()["data"]["comment"]["id"]
    with app.app_context():
        mentions = db.session.get(TaskComment, comment_id).mentions or []
    assert [m["user_id"] for m in mentions] == [seed_data["outsider_id"]]
