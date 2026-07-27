"""Regressão do enforcement de rank nas escritas de tarefa da SPA (S3/F2-5b).

Fecha a divergência entre vias para a MESMA ação: o board Kanban
(``routes/api/board.py``) e o drawer (``routes/api/task_drawer.py``) passam a
exigir rank >= editor em TODA escrita — o mesmo gate das rotas legadas
(``update_task_status``, ``finalize_task``, ``unarchive_task``) e de
``/api/tarefas/*`` (``tasks_write.py``).

Os dois lados da sprint:
    - gestor (papel de todo vínculo após o backfill da S2) mantém EXATAMENTE o
      comportamento de hoje;
    - leitor perde as escritas (status, campos, finalizar, arquivar,
      desarquivar, responsáveis, reordenar), mas segue LENDO board e drawer.

Contrato HTTP (S5/F4-2): todos os casos aqui são de rank >= leitor (o usuário VÊ
a tarefa), logo permanecem em 403 ``forbidden``. O 404 anti-enumeração vale só
para rank 0 e está coberto em ``test_api_error_envelope_contract.py``.
"""

import pytest

from models import Task, User, UserOrgao, db
from services.authorization import PAPEL_EDITOR, PAPEL_GESTOR, PAPEL_LEITOR


def _cliente_com_papel(app, seed_data, username: str, papel: str):
    """Cria usuário vinculado ao órgão dono do projeto com o papel dado e loga.

    Devolve ``(client, user_id)`` — o id permite criar tarefas em que o próprio
    usuário é AUTOR, isolando o gate de rank do gate de autoria.
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
    return _cliente_com_papel(app, seed_data, "board_leitor", PAPEL_LEITOR)


@pytest.fixture
def editor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "board_editor", PAPEL_EDITOR)


@pytest.fixture
def gestor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "board_gestor", PAPEL_GESTOR)


def _criar_tarefa(
    app,
    *,
    project_id,
    autor_id,
    status="nao_iniciada",
    ordem=1,
    is_archived=False,
) -> int:
    with app.app_context():
        task = Task(
            descricao="Tarefa do proprio autor",
            status=status,
            ordem=ordem,
            project_id=project_id,
            created_by_id=autor_id,
            is_archived=is_archived,
        )
        db.session.add(task)
        db.session.commit()
        return task.id


def _tarefa(app, task_id: int) -> Task:
    with app.app_context():
        task = db.session.get(Task, task_id)
        db.session.expunge(task)
        return task


def _erro(response) -> dict:
    payload = response.get_json()
    assert payload["ok"] is False
    return payload["error"]


# ── Board: leitura continua em rank >= leitor ────────────────────────────────


def test_board_continua_legivel_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.get("/api/tarefas/board")

    assert response.status_code == 200
    assert response.get_json()["ok"] is True


# ── Board: mudança de status exige rank >= editor ────────────────────────────


def test_api_board_status_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/status",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"
    assert _tarefa(app, seed_data["task_id"]).status == "nao_iniciada"


def test_api_board_status_permitido_para_editor(app, editor, seed_data):
    client, _ = editor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/status",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 200
    assert _tarefa(app, seed_data["task_id"]).status == "em_andamento"


def test_api_board_status_mantido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/status",
        json={"status": "em_andamento"},
    )

    assert response.status_code == 200


# ── Board: reordenação não escreve ordem/status para leitor ──────────────────


def test_api_reordenar_nao_persiste_ordem_para_leitor(app, leitor, seed_data):
    client, user_id = leitor
    primeira = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=1
    )
    segunda = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=2
    )

    response = client.post(
        "/api/tarefas/board/reordenar",
        json={"columns": [{"status": "nao_iniciada", "task_ids": [segunda, primeira]}]},
    )

    assert response.status_code == 200
    assert _tarefa(app, primeira).ordem == 1
    assert _tarefa(app, segunda).ordem == 2


def test_api_reordenar_move_entre_colunas_negado_para_leitor(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=1
    )

    response = client.post(
        "/api/tarefas/board/reordenar",
        json={
            "columns": [{"status": "em_andamento", "task_ids": [task_id]}],
            "moved_task_id": task_id,
        },
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"
    assert _tarefa(app, task_id).status == "nao_iniciada"


def test_api_reordenar_mantido_para_gestor(app, gestor, seed_data):
    client, user_id = gestor
    primeira = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=1
    )
    segunda = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, ordem=2
    )

    response = client.post(
        "/api/tarefas/board/reordenar",
        json={"columns": [{"status": "nao_iniciada", "task_ids": [segunda, primeira]}]},
    )

    assert response.status_code == 200
    assert _tarefa(app, segunda).ordem < _tarefa(app, primeira).ordem


# ── Drawer: campos inline exigem rank >= editor ──────────────────────────────


def test_api_campos_negado_para_leitor(app, leitor, seed_data):
    """Antes do gate, leitor editava campos não-restritos (tipo_pedido)."""
    client, _ = leitor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/campos",
        json={"tipo_pedido": "outros"},
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


def test_api_campos_tipo_permitido_para_editor_nao_autor(app, editor, seed_data):
    """tipo_pedido não é campo restrito: editor não-autor segue editando."""
    client, _ = editor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/campos",
        json={"tipo_pedido": "outros"},
    )

    assert response.status_code == 200
    assert _tarefa(app, seed_data["task_id"]).tipo_pedido == "outros"


def test_api_campos_mantido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.post(
        f"/api/tarefas/{seed_data['task_id']}/campos",
        json={"tipo_pedido": "outros"},
    )

    assert response.status_code == 200


# ── Drawer: rank vem ANTES da autoria (paridade com as rotas legadas) ────────


def test_api_finalizar_autor_leitor_negado(app, leitor, seed_data):
    """Mesma resposta da rota legada ``finalize_task``: 403 para autor-leitor."""
    client, user_id = leitor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/api/tarefas/{task_id}/finalizar")

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"
    assert _tarefa(app, task_id).status == "nao_iniciada"


def test_api_finalizar_autor_editor_permitido(app, editor, seed_data):
    client, user_id = editor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(f"/api/tarefas/{task_id}/finalizar")

    assert response.status_code == 200
    assert _tarefa(app, task_id).status == "finalizada"


def test_api_arquivar_autor_leitor_negado(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(
        app, project_id=seed_data["project_id"], autor_id=user_id, status="finalizada"
    )

    response = client.post(f"/api/tarefas/{task_id}/arquivar")

    assert response.status_code == 403
    assert _tarefa(app, task_id).is_archived is not True


def test_api_desarquivar_autor_leitor_negado(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(
        app,
        project_id=seed_data["project_id"],
        autor_id=user_id,
        status="finalizada",
        is_archived=True,
    )

    response = client.post(f"/api/tarefas/{task_id}/desarquivar")

    assert response.status_code == 403
    assert _tarefa(app, task_id).is_archived is True


def test_api_reativar_autor_gestor_mantido(app, gestor, seed_data):
    client, user_id = gestor
    task_id = _criar_tarefa(
        app,
        project_id=seed_data["project_id"],
        autor_id=user_id,
        status="finalizada",
        is_archived=True,
    )

    response = client.post(f"/api/tarefas/{task_id}/reativar")

    assert response.status_code == 200
    assert _tarefa(app, task_id).is_archived is not True


def test_api_responsaveis_autor_leitor_negado(app, leitor, seed_data):
    client, user_id = leitor
    task_id = _criar_tarefa(app, project_id=seed_data["project_id"], autor_id=user_id)

    response = client.post(
        f"/api/tarefas/{task_id}/responsaveis", json={"user_ids": []}
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


# ── Drawer: can_edit do Detalhe de Projeto reflete o rank (F2-7) ─────────────


def test_detalhe_de_projeto_esconde_edicao_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = client.get(f"/api/projetos/{seed_data['project_id']}/detalhe")

    assert response.status_code == 200
    assert response.get_json()["data"]["permissions"]["can_edit"] is False


def test_detalhe_de_projeto_mantem_edicao_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = client.get(f"/api/projetos/{seed_data['project_id']}/detalhe")

    assert response.status_code == 200
    assert response.get_json()["data"]["permissions"]["can_edit"] is True
