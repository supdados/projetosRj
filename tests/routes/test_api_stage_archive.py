"""Arquivar concluídas no drawer "Tarefas da etapa" (StageArchiveReview).

O drawer não tem filtro de etapa no lote: manda ``project`` + os ``task_ids``
das finalizadas listadas. Estes testes fixam esse contrato — o lote não vaza
para outras etapas do projeto e a tarefa desmarcada na revisão fica na etapa.
"""

import pytest

from models import Etapa, Task, db

URL_LOTE = "/api/tarefas/arquivar-finalizadas"


@pytest.fixture
def stage_tasks(app, seed_data) -> dict[str, int]:
    with app.app_context():
        outra_etapa = Etapa.query.filter_by(
            project_id=seed_data["project_id"], descricao="Etapa Iniciada"
        ).one()

        def finalizada(descricao: str, etapa_id: int) -> Task:
            return Task(
                descricao=descricao,
                status="finalizada",
                project_id=seed_data["project_id"],
                etapa_id=etapa_id,
                created_by_id=seed_data["user_id"],
            )

        marcada = finalizada("Concluída marcada", seed_data["etapa_id"])
        desmarcada = finalizada("Concluída desmarcada", seed_data["etapa_id"])
        vizinha = finalizada("Concluída de outra etapa", outra_etapa.id)
        db.session.add_all([marcada, desmarcada, vizinha])
        db.session.commit()
        return {
            "marcada": marcada.id,
            "desmarcada": desmarcada.id,
            "vizinha": vizinha.id,
        }


def test_preview_da_etapa_fica_nos_ids_enviados(client_user, seed_data, stage_tasks):
    ids_da_etapa = [stage_tasks["marcada"], stage_tasks["desmarcada"]]
    response = client_user.post(
        URL_LOTE,
        json={
            "project": str(seed_data["project_id"]),
            "task_ids": ids_da_etapa,
            "preview": True,
        },
    )
    assert response.status_code == 200
    assert sorted(response.get_json()["data"]["task_ids"]) == sorted(ids_da_etapa)


def test_arquiva_so_a_marcada_e_some_da_lista_da_etapa(
    app, client_user, seed_data, stage_tasks
):
    response = client_user.post(
        URL_LOTE,
        json={
            "project": str(seed_data["project_id"]),
            "task_ids": [stage_tasks["marcada"]],
        },
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["archived_task_ids"] == [
        str(stage_tasks["marcada"])
    ]

    listing = client_user.get(
        f"/api/projetos/{seed_data['project_id']}/etapas/{seed_data['etapa_id']}/tarefas"
    )
    listed_ids = {task["id"] for task in listing.get_json()["data"]["tarefas"]}
    assert stage_tasks["marcada"] not in listed_ids
    assert stage_tasks["desmarcada"] in listed_ids
    with app.app_context():
        assert not db.session.get(Task, stage_tasks["desmarcada"]).is_archived
        assert not db.session.get(Task, stage_tasks["vizinha"]).is_archived


def test_preview_devolve_as_linhas_do_card_de_revisao(
    client_user, seed_data, stage_tasks
):
    response = client_user.post(
        URL_LOTE,
        json={"task_ids": [stage_tasks["marcada"]], "preview": True},
    )
    assert response.status_code == 200
    (linha,) = response.get_json()["data"]["tarefas"]
    assert linha["id"] == stage_tasks["marcada"]
    assert linha["descricao"] == "Concluída marcada"
    assert linha["project_titulo"]
    assert linha["assignees"] == []
