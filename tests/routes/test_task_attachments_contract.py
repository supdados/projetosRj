import io
from pathlib import Path

import routes.tasks.helpers as task_helpers
from models import TaskAnexo, db


def test_task_attachment_flow_covers_upload_list_view_delete_and_cleanup(
    app, client_user, seed_data, monkeypatch, tmp_path
):
    monkeypatch.setattr(task_helpers, "_get_upload_folder", lambda: str(tmp_path))

    upload_response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/anexos/add",
        data={"file": (io.BytesIO(b"conteudo do anexo"), "evidencia.txt")},
        content_type="multipart/form-data",
    )

    assert upload_response.status_code == 200
    upload_payload = upload_response.get_json()
    assert upload_payload["success"] is True
    assert upload_payload["anexo"]["filename"] == "evidencia.txt"
    assert upload_payload["anexo"]["content_type"] == "text/plain"
    assert upload_payload["anexos_count"] == 1

    anexo_id = upload_payload["anexo"]["id"]

    with app.app_context():
        anexo = db.session.get(TaskAnexo, anexo_id)
        assert anexo is not None
        stored_path = Path(tmp_path) / anexo.stored_filename
        assert stored_path.exists()

    list_response = client_user.get(f"/tarefas/{seed_data['task_id']}/anexos")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["success"] is True
    assert list_payload["count"] == 1
    assert list_payload["anexos"][0]["id"] == anexo_id
    assert list_payload["anexos"][0]["filename"] == "evidencia.txt"

    view_response = client_user.get(f"/tarefas/anexos/{anexo_id}")
    assert view_response.status_code == 200
    assert view_response.data == b"conteudo do anexo"

    delete_response = client_user.post(f"/tarefas/anexos/{anexo_id}/delete")
    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["success"] is True
    assert delete_payload["anexos_count"] == 0

    with app.app_context():
        assert db.session.get(TaskAnexo, anexo_id) is None
        assert not stored_path.exists()


def test_task_item_attachment_alias_and_invalid_extension_are_handled(
    client_user, seed_data, monkeypatch, tmp_path
):
    monkeypatch.setattr(task_helpers, "_get_upload_folder", lambda: str(tmp_path))

    alias_upload_response = client_user.post(
        f"/tarefas/itens/{seed_data['task_item_id']}/anexos/add",
        data={"file": (io.BytesIO(b"%PDF-1.4 conteudo"), "anexo.pdf")},
        content_type="multipart/form-data",
    )

    assert alias_upload_response.status_code == 200
    alias_payload = alias_upload_response.get_json()
    assert alias_payload["success"] is True
    assert alias_payload["anexo"]["filename"] == "anexo.pdf"
    assert alias_payload["anexo"]["content_type"] == "application/pdf"

    alias_list_response = client_user.get(
        f"/tarefas/itens/{seed_data['task_item_id']}/anexos"
    )
    assert alias_list_response.status_code == 200
    alias_list_payload = alias_list_response.get_json()
    assert alias_list_payload["success"] is True
    assert alias_list_payload["count"] == 1
    assert alias_list_payload["anexos"][0]["filename"] == "anexo.pdf"

    invalid_response = client_user.post(
        f"/tarefas/{seed_data['task_id']}/anexos/add",
        data={"file": (io.BytesIO(b"binario"), "malicioso.exe")},
        content_type="multipart/form-data",
    )

    assert invalid_response.status_code == 400
    invalid_payload = invalid_response.get_json()
    assert invalid_payload["success"] is False
    assert "não permitido" in invalid_payload["message"].lower()
