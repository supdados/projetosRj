"""Regressão do enforcement de rank nos ANEXOS de tarefa (extensão S3/F2-5b).

Prova os dois lados exigidos pela sprint:
    - gestor (papel de todo vínculo após o backfill da S2) mantém o upload;
    - editor mantém o upload; leitor perde upload mas mantém a leitura.

A exclusão foi alinhada à rota API (``api_anexo_delete``): autor da tarefa ou
admin (``_can_manage_task_restricted_actions``) nas DUAS vias — fecha a
inconsistência em que a rota legada deixava qualquer usuário com visão excluir
anexo alheio.

Contrato HTTP (S5/F4-2): rank 0 responde **404 ``not_found``** com o corpo
canônico do id inexistente; 403 fica para quem vê a tarefa (leitor no upload,
não-autor na exclusão).
"""

import io
import time
import uuid

import pytest

from models import TaskAnexo, User, UserOrgao, db
from services.authorization import PAPEL_EDITOR, PAPEL_GESTOR, PAPEL_LEITOR

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 16

RESTRICTED_DELETE_MESSAGE = (
    "Somente o autor da tarefa ou um administrador pode excluir anexos."
)


def _cliente_com_papel(app, seed_data, username: str, papel: str):
    """Cria usuário vinculado ao órgão dono do projeto com o papel dado e loga."""
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
        session["login_at"] = time.time()
    return client, user_id


@pytest.fixture
def leitor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "anexos_leitor", PAPEL_LEITOR)


@pytest.fixture
def editor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "anexos_editor", PAPEL_EDITOR)


@pytest.fixture
def gestor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "anexos_gestor", PAPEL_GESTOR)


def _criar_anexo_sem_arquivo(app, *, task_id: int, uploaded_by_id: int) -> int:
    """Anexo só em banco (sem arquivo físico): a exclusão tolera OSError."""
    with app.app_context():
        anexo = TaskAnexo(
            task_id=task_id,
            filename="doc.txt",
            stored_filename=f"{uuid.uuid4()}.txt",
            content_type="text/plain",
            uploaded_by_id=uploaded_by_id,
        )
        db.session.add(anexo)
        db.session.commit()
        return anexo.id


def _upload_legado(client, task_id: int):
    return client.post(
        f"/tarefas/{task_id}/anexos/add",
        data={"file": (io.BytesIO(_PNG_BYTES), "captura.png")},
        content_type="multipart/form-data",
    )


def _upload_api(client, task_id: int):
    return client.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(_PNG_BYTES), "captura.png")},
        content_type="multipart/form-data",
    )


def _anexo_existe(app, anexo_id: int) -> bool:
    with app.app_context():
        return db.session.get(TaskAnexo, anexo_id) is not None


# ── Upload (rank >= editor) ──────────────────────────────────────────────────


def test_upload_legado_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = _upload_legado(client, seed_data["task_id"])

    assert response.status_code == 403
    assert response.get_json()["message"] == "Sem permissão"


def test_upload_api_negado_para_leitor(app, leitor, seed_data):
    client, _ = leitor

    response = _upload_api(client, seed_data["task_id"])

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_upload_legado_permitido_para_editor(app, editor, seed_data):
    client, _ = editor

    response = _upload_legado(client, seed_data["task_id"])

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_upload_api_permitido_para_editor(app, editor, seed_data):
    client, _ = editor

    response = _upload_api(client, seed_data["task_id"])

    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_upload_legado_permitido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = _upload_legado(client, seed_data["task_id"])

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_upload_api_permitido_para_gestor(app, gestor, seed_data):
    client, _ = gestor

    response = _upload_api(client, seed_data["task_id"])

    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_upload_api_rank_zero_responde_404(app, client_outsider, seed_data):
    """S5/F4-2: tarefa invisível responde o MESMO 404 da tarefa inexistente."""
    fora_do_escopo = _upload_api(client_outsider, seed_data["task_id"])
    inexistente = _upload_api(client_outsider, 999999)

    assert fora_do_escopo.status_code == 404
    assert fora_do_escopo.get_json()["error"]["code"] == "not_found"
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_upload_legado_rank_zero_responde_404(app, client_outsider, seed_data):
    """Mesma decisão na superfície legada (``jsonify``)."""
    fora_do_escopo = _upload_legado(client_outsider, seed_data["task_id"])
    inexistente = _upload_legado(client_outsider, 999999)

    assert fora_do_escopo.status_code == 404
    assert fora_do_escopo.get_json() == inexistente.get_json()


# ── Leitura preservada (rank >= leitor) ──────────────────────────────────────


def test_leitor_ainda_lista_anexos(app, leitor, seed_data):
    client, _ = leitor

    legado = client.get(f"/tarefas/{seed_data['task_id']}/anexos")
    api = client.get(f"/api/tarefas/{seed_data['task_id']}/anexos")

    assert legado.status_code == 200
    assert api.status_code == 200


# ── Exclusão legada alinhada à API (autor/admin) ─────────────────────────────


def test_delete_legado_negado_para_editor_nao_autor(app, editor, seed_data):
    client, _ = editor
    anexo_id = _criar_anexo_sem_arquivo(
        app, task_id=seed_data["task_id"], uploaded_by_id=seed_data["user_id"]
    )

    response = client.post(f"/tarefas/anexos/{anexo_id}/delete")

    assert response.status_code == 403
    assert response.get_json()["message"] == RESTRICTED_DELETE_MESSAGE
    assert _anexo_existe(app, anexo_id)


def test_delete_legado_negado_para_gestor_nao_autor(app, gestor, seed_data):
    """Paridade com api_anexo_delete: gestor não herda a ação restrita (§9.1)."""
    client, _ = gestor
    anexo_id = _criar_anexo_sem_arquivo(
        app, task_id=seed_data["task_id"], uploaded_by_id=seed_data["user_id"]
    )

    response = client.post(f"/tarefas/anexos/{anexo_id}/delete")

    assert response.status_code == 403
    assert _anexo_existe(app, anexo_id)


def test_delete_legado_permitido_para_autor_da_tarefa(app, client_user, seed_data):
    anexo_id = _criar_anexo_sem_arquivo(
        app, task_id=seed_data["task_id"], uploaded_by_id=seed_data["user_id"]
    )

    response = client_user.post(f"/tarefas/anexos/{anexo_id}/delete")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert not _anexo_existe(app, anexo_id)


def test_delete_legado_permitido_para_admin(app, client_admin, seed_data):
    anexo_id = _criar_anexo_sem_arquivo(
        app, task_id=seed_data["task_id"], uploaded_by_id=seed_data["user_id"]
    )

    response = client_admin.post(f"/tarefas/anexos/{anexo_id}/delete")

    assert response.status_code == 200
    assert not _anexo_existe(app, anexo_id)
