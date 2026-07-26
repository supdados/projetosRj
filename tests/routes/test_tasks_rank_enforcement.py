"""Regressão do enforcement de rank nas escritas de TAREFA (S3/F2-5).

Prova os dois lados exigidos pela sprint:
    - gestor (papel de todo vínculo após o backfill da S2) mantém EXATAMENTE o
      comportamento de hoje — nenhum usuário real perde acesso no deploy;
    - editor mantém as escritas de tarefa de projeto; leitor perde todas elas.

Invariantes que a sprint NÃO mexe (decisão de produto, §9.1):
    - finalizar/excluir tarefa alheia continua "admin ou autor" — gestor não herda;
    - tarefa avulsa (``project_id IS NULL``) continua restrita ao criador/admin,
      sem qualquer relação com rank de projeto;
    - comentar continua em rank >= leitor.

Contrato HTTP preservado: rank insuficiente — inclusive rank 0 — continua 403;
a unificação 404 anti-enumeração é da S5.
"""

import pytest

from models import Task, User, UserOrgao, db
from routes.tasks.crud import DELETE_DENIED_MESSAGE
from routes.tasks.permissions import FINALIZE_DENIED_MESSAGE
from services.authorization import PAPEL_EDITOR, PAPEL_GESTOR, PAPEL_LEITOR

AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def _cliente_com_papel(app, seed_data, username: str, papel: str):
    """Cria usuário vinculado ao órgão dono do projeto com o papel dado e loga.

    Devolve ``(client, user_id)`` — o id é necessário para criar tarefas em que
    o próprio usuário é AUTOR, isolando o gate de rank do gate de autoria.
    """
    with app.app_context():
        user = User(username=username, name=username, orgao="Orgao Teste")
        user.set_password("senha123")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            UserOrgao(
                user_id=user.id,
                orgao_id=seed_data["auditoria_orgao_id"],
                papel=papel,
            )
        )
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client, user_id


@pytest.fixture
def leitor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "tarefas_leitor", PAPEL_LEITOR)


@pytest.fixture
def editor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "tarefas_editor", PAPEL_EDITOR)


@pytest.fixture
def gestor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "tarefas_gestor", PAPEL_GESTOR)


def _criar_tarefa(app, *, project_id, autor_id, status="nao_iniciada", ordem=1) -> int:
    with app.app_context():
        task = Task(
            descricao="Tarefa do proprio autor",
            status=status,
            ordem=ordem,
            project_id=project_id,
            created_by_id=autor_id,
        )
        db.session.add(task)
        db.session.commit()
        return task.id


def _status_da_tarefa(app, task_id: int) -> str:
    with app.app_context():
        return db.session.get(Task, task_id).status


def _arquivada(app, task_id: int) -> bool:
    with app.app_context():
        return bool(db.session.get(Task, task_id).is_archived)


def _erro(response) -> dict:
    payload = response.get_json()
    assert payload["ok"] is False
    return payload["error"]


# ── Criar tarefa de projeto (rank >= editor) ─────────────────────────────────


def test_criar_tarefa_de_projeto_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        "/tarefas/add",
        data={"project": str(seed_data["project_id"]), "descricao": "Nao deveria"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 403
    assert response.get_json()["message"] == "Sem permissão para este projeto."


def test_criar_tarefa_de_projeto_permitido_para_editor(app, editor, seed_data):
    client, _ = editor

    response = client.post(
        "/tarefas/add",
        data={"project": str(seed_data["project_id"]), "descricao": "Tarefa editor"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_criar_tarefa_de_projeto_permitido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        "/tarefas/add",
        data={"project": str(seed_data["project_id"]), "descricao": "Tarefa gestor"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_api_criar_tarefa_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        "/api/tarefas",
        json={"project_id": seed_data["project_id"], "descricao": "Nao deveria"},
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


def test_api_criar_tarefa_permitido_para_editor(app, editor, seed_data):
    client, _ = editor

    response = client.post(
        "/api/tarefas",
        json={"project_id": seed_data["project_id"], "descricao": "Tarefa editor"},
    )

    assert response.status_code == 200


def test_api_criar_tarefa_permitido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        "/api/tarefas",
        json={"project_id": seed_data["project_id"], "descricao": "Tarefa gestor"},
    )

    assert response.status_code == 200


def test_api_criar_tarefa_rank_zero_continua_403(app, client_outsider, seed_data):
    """Contrato desta fase: fora de escopo é 403; o 404 anti-enumeração é S5."""
    response = client_outsider.post(
        "/api/tarefas",
        json={"project_id": seed_data["project_id"], "descricao": "Fora de escopo"},
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


# ── Editar tarefa de projeto (rank >= editor) ────────────────────────────────


def test_editar_tarefa_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/edit",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 403
    assert _status_da_tarefa(app, seed_data["task_id"]) == "nao_iniciada"


def test_editar_tarefa_permitido_para_editor(app, editor, seed_data):
    client, _ = editor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/edit",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 200
    assert _status_da_tarefa(app, seed_data["task_id"]) == "em_andamento"


def test_editar_tarefa_permitido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/edit",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 200
    assert _status_da_tarefa(app, seed_data["task_id"]) == "em_andamento"


def test_update_status_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/update_status",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 403
    assert _status_da_tarefa(app, seed_data["task_id"]) == "nao_iniciada"


def test_update_status_permitido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/update_status",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 200


def test_update_prioridade_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/update_prioridade",
        json={"prioridade": "alta"},
    )

    assert response.status_code == 403


def test_update_tipo_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/update_tipo",
        json={"tipo_pedido": "outros"},
    )

    assert response.status_code == 403


def test_mover_etapa_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/mover-etapa",
        json={"etapa": seed_data["etapa_id"]},
    )

    assert response.status_code == 403


def test_mover_etapa_permitido_para_editor(app, editor, seed_data):
    client, _ = editor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/mover-etapa",
        json={"etapa": seed_data["etapa_id"]},
    )

    assert response.status_code == 200


def test_api_mover_etapa_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/mover-etapa",
        json={"etapa_id": seed_data["etapa_id"]},
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


def test_api_mover_etapa_permitido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/mover-etapa",
        json={"etapa_id": seed_data["etapa_id"]},
    )

    assert response.status_code == 200


# ── Excluir/finalizar: rank ANTES da autoria (autor leitor perde a escrita) ──


def test_excluir_propria_tarefa_negado_para_leitor(app, leitor, seed_data):
    """Autor rebaixado a leitor perde a escrita — o rank vem antes da autoria."""
    client, user_id = leitor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/tarefas/{task_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 403
    with app.app_context():
        assert db.session.get(Task, task_id) is not None


def test_excluir_propria_tarefa_permitido_para_editor(app, editor, seed_data):
    client, user_id = editor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/tarefas/{task_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id) is None


def test_api_excluir_propria_tarefa_permitido_para_gestor(app, gestor, seed_data):
    client, user_id = gestor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/api/tarefas/{task_id}/excluir")

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id) is None


def test_api_excluir_propria_tarefa_negado_para_leitor(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/api/tarefas/{task_id}/excluir")

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


def test_finalizar_propria_tarefa_permitido_para_editor(app, editor, seed_data):
    client, user_id = editor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/tarefas/{task_id}/finalizar", headers=AJAX_HEADERS)

    assert response.status_code == 200
    assert _status_da_tarefa(app, task_id) == "finalizada"


def test_finalizar_propria_tarefa_negado_para_leitor(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/tarefas/{task_id}/finalizar", headers=AJAX_HEADERS)

    assert response.status_code == 403
    assert _status_da_tarefa(app, task_id) == "nao_iniciada"


# ── INTOCADO: ações restritas seguem "admin ou autor" (gestor não herda) ─────


def test_gestor_nao_exclui_tarefa_alheia(app, gestor, seed_data):
    """``_can_manage_task_restricted_actions`` não foi estendido ao gestor (§9.1)."""
    client, _ = gestor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/delete", headers=AJAX_HEADERS
    )

    assert response.status_code == 403
    assert response.get_json()["message"] == DELETE_DENIED_MESSAGE


def test_gestor_nao_finaliza_tarefa_alheia(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/finalizar", headers=AJAX_HEADERS
    )

    assert response.status_code == 403
    assert response.get_json()["message"] == FINALIZE_DENIED_MESSAGE


def test_api_gestor_nao_exclui_tarefa_alheia(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(f"/api/tarefas/{seed_data['task_id']}/excluir")

    assert response.status_code == 403
    assert _erro(response)["message"] == DELETE_DENIED_MESSAGE


def test_gestor_nao_finaliza_via_edit_tarefa_alheia(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/edit", json={"status": "finalizada"}
    )

    assert response.status_code == 403
    assert response.get_json()["message"] == FINALIZE_DENIED_MESSAGE


# ── INTOCADO: tarefa avulsa não depende de rank e não vaza ───────────────────


def test_leitor_cria_e_edita_tarefa_avulsa(app, leitor):
    """Sem projeto não há rank: a tarefa avulsa continua sendo do criador."""
    client, _ = leitor

    criada = client.post(
        "/tarefas/add",
        data={"descricao": "Avulsa do leitor"},
        headers=AJAX_HEADERS,
    )
    assert criada.status_code == 200
    task_id = criada.get_json()["task"]["id"]

    editada = client.post(f"/tarefas/{task_id}/edit", json={"status": "em_andamento"})

    assert editada.status_code == 200
    assert _status_da_tarefa(app, task_id) == "em_andamento"


def test_leitor_exclui_a_propria_tarefa_avulsa(app, leitor):
    client, _ = leitor

    criada = client.post(
        "/tarefas/add", data={"descricao": "Avulsa"}, headers=AJAX_HEADERS
    )
    task_id = criada.get_json()["task"]["id"]

    response = client.post(f"/tarefas/{task_id}/delete", headers=AJAX_HEADERS)

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id) is None


def test_tarefa_avulsa_alheia_nao_vaza_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/tarefas/{seed_data['orphan_task_id']}/edit", json={"status": "em_andamento"}
    )

    assert response.status_code == 403


def test_api_tarefa_avulsa_alheia_nao_vaza_para_editor(app, editor, seed_data):
    client, _ = editor

    response = client.post(f"/api/tarefas/{seed_data['orphan_task_id']}/excluir")

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


# ── Leitura e comentário continuam em rank >= leitor ─────────────────────────


def test_leitor_continua_comentando(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/tarefas/{seed_data['task_id']}/comentarios/add",
        data={"content": "Comentario de leitor"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_leitor_continua_vendo_sugestoes_de_responsavel(app, leitor, seed_data):
    client, _ = leitor

    response = client.get(
        f"/tarefas/sugestoes-responsavel?project={seed_data['project_id']}"
    )

    assert response.status_code == 200
    assert "users" in response.get_json()


def test_leitor_continua_vendo_a_tarefa_no_drawer(app, leitor, seed_data):
    client, _ = leitor

    response = client.get(f"/api/tarefas/{seed_data['task_id']}/detalhe")

    assert response.status_code == 200


# ── Lote e reordenação: escrita não escapa pelo caminho em massa ─────────────


def test_arquivar_finalizadas_ignora_tarefa_de_quem_so_le(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(
        app,
        project_id=seed_data["project_id"],
        autor_id=user_id,
        status="finalizada",
    )

    response = client.post(
        "/tarefas/arquivar-finalizadas", json={}, headers=AJAX_HEADERS
    )

    assert response.status_code == 200
    assert _arquivada(app, task_id) is False


def test_arquivar_finalizadas_mantido_para_gestor(app, gestor, seed_data):
    client, user_id = gestor
    task_id = _criar_tarefa(
        app,
        project_id=seed_data["project_id"],
        autor_id=user_id,
        status="finalizada",
    )

    response = client.post(
        "/tarefas/arquivar-finalizadas", json={}, headers=AJAX_HEADERS
    )

    assert response.status_code == 200
    assert _arquivada(app, task_id) is True


def test_api_arquivar_finalizadas_ignora_tarefa_de_quem_so_le(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(
        app,
        project_id=seed_data["project_id"],
        autor_id=user_id,
        status="finalizada",
    )

    response = client.post("/api/tarefas/arquivar-finalizadas", json={})

    assert response.status_code == 200
    assert response.get_json()["data"]["archived_count"] == 0
    assert _arquivada(app, task_id) is False


def _ordem_das_tarefas(app, task_ids: list[int]) -> list[int]:
    with app.app_context():
        return [db.session.get(Task, task_id).ordem for task_id in task_ids]


def test_reordenar_nao_altera_ordem_para_leitor(app, leitor, seed_data):
    client, user_id = leitor
    primeira = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=1
    )
    segunda = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=2
    )

    response = client.post("/tarefas/reordenar", json={"ordem": [segunda, primeira]})

    assert response.status_code == 200
    assert _ordem_das_tarefas(app, [primeira, segunda]) == [1, 2]


def test_reordenar_mantido_para_gestor(app, gestor, seed_data):
    client, user_id = gestor
    primeira = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=1
    )
    segunda = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=2
    )

    response = client.post("/tarefas/reordenar", json={"ordem": [segunda, primeira]})

    assert response.status_code == 200
    ordem_primeira, ordem_segunda = _ordem_das_tarefas(app, [primeira, segunda])
    assert ordem_segunda < ordem_primeira
