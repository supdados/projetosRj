"""P2-07: arquivos só são removidos depois do commit da exclusão."""

import io
from pathlib import Path

import pytest

from models import Task, TaskAnexo, db


class TemporaryUploadFolder:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __call__(self) -> str:
        return str(self.path)


@pytest.fixture
def uploaded_file(
    app, client_user, seed_data, monkeypatch, tmp_path
) -> tuple[int, Path]:
    folder = TemporaryUploadFolder(tmp_path)
    monkeypatch.setattr("routes.api.task_attachments._get_upload_folder", folder)
    monkeypatch.setattr("routes.tasks.constants._get_upload_folder", folder)
    monkeypatch.setattr("routes.tasks.helpers._get_upload_folder", folder)
    response = client_user.post(
        f"/api/tarefas/{seed_data['task_id']}/anexos",
        data={"file": (io.BytesIO(b"conteudo temporario"), "evidencia.txt")},
    )
    assert response.status_code == 200
    attachment_id = response.get_json()["data"]["anexo"]["id"]
    with app.app_context():
        filename = db.session.get(TaskAnexo, attachment_id).stored_filename
    return attachment_id, tmp_path / filename


def test_delete_task_removes_attachment_files(
    app, client_user, seed_data, uploaded_file
) -> None:
    attachment_id, file_path = uploaded_file
    assert file_path.exists()
    response = client_user.post(f"/api/tarefas/{seed_data['task_id']}/excluir")
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Task, seed_data["task_id"]) is None
        assert db.session.get(TaskAnexo, attachment_id) is None
    assert not file_path.exists()


def test_delete_task_removes_all_its_files_only(
    app, client_user, seed_data, uploaded_file
) -> None:
    _, first_path = uploaded_file
    second = client_user.post(
        f"/api/tarefas/{seed_data['task_id']}/anexos",
        data={"file": (io.BytesIO(b"segundo"), "segundo.txt")},
    )
    assert second.status_code == 200
    with app.app_context():
        second_name = db.session.get(
            TaskAnexo, second.get_json()["data"]["anexo"]["id"]
        ).stored_filename
    preserved = first_path.parent / "arquivo_de_outra_tarefa.txt"
    preserved.write_text("preservar")
    assert (
        client_user.post(f"/api/tarefas/{seed_data['task_id']}/excluir").status_code
        == 200
    )
    assert not first_path.exists()
    assert not (first_path.parent / second_name).exists()
    assert preserved.read_text() == "preservar"


def test_denied_task_delete_preserves_file(
    client_editable, seed_data, uploaded_file
) -> None:
    _, file_path = uploaded_file
    assert (
        client_editable.post(f"/api/tarefas/{seed_data['task_id']}/excluir").status_code
        == 403
    )
    assert file_path.exists()


@pytest.mark.parametrize("prefix", ["/api/anexos", "/tarefas/anexos"])
def test_single_attachment_delete_uses_the_same_cleanup(
    client_user, uploaded_file, prefix
) -> None:
    attachment_id, file_path = uploaded_file
    assert client_user.post(f"{prefix}/{attachment_id}/delete").status_code == 200
    assert not file_path.exists()


class FailingFileDeletionCommit:
    def __call__(self) -> None:
        db.session.flush()
        raise RuntimeError("Commit de exclusão recusado")


@pytest.mark.parametrize("operation", ["task", "attachment", "legacy_attachment"])
def test_failed_commit_preserves_record_and_file(
    app, client_user, seed_data, uploaded_file, monkeypatch, operation
) -> None:
    attachment_id, file_path = uploaded_file
    monkeypatch.setattr(db.session, "commit", FailingFileDeletionCommit())
    paths = {
        "task": f"/api/tarefas/{seed_data['task_id']}/excluir",
        "attachment": f"/api/anexos/{attachment_id}/delete",
        "legacy_attachment": f"/tarefas/anexos/{attachment_id}/delete",
    }
    response = client_user.post(paths[operation])
    assert response.status_code in (422, 500)
    with app.app_context():
        assert db.session.get(Task, seed_data["task_id"]) is not None
        assert db.session.get(TaskAnexo, attachment_id) is not None
    assert file_path.read_bytes() == b"conteudo temporario"
