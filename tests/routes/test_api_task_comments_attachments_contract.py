"""Testes de contrato dos endpoints de COMENTÁRIOS e ANEXOS do drawer (Fase 5b-2).

Afirmam o envelope canônico ``{"ok": true, "data": ...}`` /
``{"ok": false, "error": {"code", "message"}}`` de:

    - COMENTÁRIOS: POST /api/tarefas/<id>/comentarios (add) ; POST
      /api/comentarios/<id> (editar) ; POST /api/comentarios/<id>/delete.
    - ANEXOS: GET /api/tarefas/<id>/anexos (listar) ; POST /api/tarefas/<id>/anexos
      (UPLOAD multipart request.files["file"]) ; GET /api/anexos/<id> (DOWNLOAD
      binário send_file — NÃO envelopado) ; POST /api/anexos/<id>/delete.

Cobrem os guards/validações: 200, 401 (sem sessão), 403 (editar comentário
alheio / excluir anexo sem ser autor), 422 (conteúdo vazio / arquivo inválido) e
413 (upload acima do limite). O download é binário (200, bytes). Reutilizam as
fixtures de ``tests/conftest.py`` (``client`` anônimo, ``client_user`` = autor,
``client_outsider`` = fora do escopo) e o banco semeado. Sem mocks de rede.
"""

from __future__ import annotations

import io
from typing import Any

#: PNG mínimo válido (8 magic bytes + restante) que passa em
#: ``_file_content_matches_extension`` (assinatura ``\x89PNG\r\n\x1a\n``).
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _assert_ok_envelope(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "data" in payload
    assert "error" not in payload
    return payload["data"]


def _assert_fail_envelope(payload: Any, *, code: str) -> None:
    assert isinstance(payload, dict)
    assert payload["ok"] is False
    assert "data" not in payload
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]


# ---------------------------------------------------------------------------
# COMENTÁRIOS
# ---------------------------------------------------------------------------


def test_api_comentario_add_creates_and_returns_list(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/comentarios",
        json={"content": "Novo comentário via drawer"},
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["comment"]["content"] == "Novo comentário via drawer"
    assert data["comment"]["is_own"] is True
    assert data["comment"]["can_edit"] is True
    # sem segredos do autor
    assert "password_hash" not in data["comment"]
    assert any(c["id"] == data["comment"]["id"] for c in data["comentarios"])


def test_api_comentario_add_empty_is_422(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/comentarios", json={"content": "   "}
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_comentario_add_requires_session(client, seed_data):
    task_id = seed_data["task_id"]
    response = client.post(
        f"/api/tarefas/{task_id}/comentarios", json={"content": "oi"}
    )

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_comentario_add_unknown_task_is_404(client_user):
    response = client_user.post(
        "/api/tarefas/999999/comentarios", json={"content": "oi"}
    )

    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_api_comentario_edit_own_succeeds(client_user, seed_data):
    comment_id = seed_data["comment_id"]
    response = client_user.post(
        f"/api/comentarios/{comment_id}", json={"content": "Editado"}
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["comment"]["id"] == comment_id
    assert data["comment"]["content"] == "Editado"


def test_api_comentario_edit_foreign_is_403(client_user, seed_data):
    """Editar comentário de outro autor é recusado (autoridade server-side)."""
    foreign_comment_id = seed_data["foreign_comment_id"]
    response = client_user.post(
        f"/api/comentarios/{foreign_comment_id}", json={"content": "hack"}
    )

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


def test_api_comentario_edit_empty_is_422(client_user, seed_data):
    comment_id = seed_data["comment_id"]
    response = client_user.post(f"/api/comentarios/{comment_id}", json={"content": ""})

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_comentario_delete_own_succeeds(client_user, seed_data):
    comment_id = seed_data["comment_id"]
    response = client_user.post(f"/api/comentarios/{comment_id}/delete")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["comment_id"] == comment_id
    assert all(c["id"] != comment_id for c in data["comentarios"])


def test_api_comentario_delete_foreign_is_403(client_user, seed_data):
    foreign_comment_id = seed_data["foreign_comment_id"]
    response = client_user.post(f"/api/comentarios/{foreign_comment_id}/delete")

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# ANEXOS — listar / upload / download / excluir
# ---------------------------------------------------------------------------


def test_api_anexos_list_starts_empty(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.get(f"/api/tarefas/{task_id}/anexos")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["count"] == 0
    assert data["anexos"] == []


def test_api_anexo_upload_multipart_creates_attachment(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(_PNG_BYTES), "captura.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["anexo"]["filename"] == "captura.png"
    assert data["anexo"]["is_image"] is True
    assert data["count"] == 1
    # NÃO expor o nome físico no disco
    assert "stored_filename" not in data["anexo"]
    assert data["anexo"]["url"].startswith("/api/anexos/")


def test_api_anexo_upload_invalid_extension_is_422(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(b"#!/bin/sh\n"), "script.sh")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_anexo_upload_content_mismatch_is_422(client_user, seed_data):
    """Extensão permitida mas conteúdo não bate com a assinatura => 422."""
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(b"not really a png"), "fake.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_anexo_upload_no_file_is_422(client_user, seed_data):
    task_id = seed_data["task_id"]
    response = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_anexo_upload_over_limit_is_413(client_user, seed_data, app):
    """Upload acima de ``MAX_CONTENT_LENGTH`` => 413 envelopado (validation).

    Reduz o limite em runtime (sem alterar config.py) para forçar o
    ``RequestEntityTooLarge`` do Flask, capturado por ``api_payload_too_large``.
    """
    task_id = seed_data["task_id"]
    original_limit = app.config.get("MAX_CONTENT_LENGTH")
    app.config["MAX_CONTENT_LENGTH"] = 16
    try:
        big = _PNG_BYTES + b"0" * 1024
        response = client_user.post(
            f"/api/tarefas/{task_id}/anexos",
            data={"file": (io.BytesIO(big), "grande.png")},
            content_type="multipart/form-data",
        )
    finally:
        app.config["MAX_CONTENT_LENGTH"] = original_limit

    assert response.status_code == 413
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_anexo_upload_requires_session(client, seed_data):
    task_id = seed_data["task_id"]
    response = client.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(_PNG_BYTES), "x.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_anexo_download_returns_binary_200(client_user, seed_data):
    """Upload e depois baixa: o download é binário (NÃO envelopado)."""
    task_id = seed_data["task_id"]
    upload = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(_PNG_BYTES), "img.png")},
        content_type="multipart/form-data",
    )
    anexo_id = _assert_ok_envelope(upload.get_json())["anexo"]["id"]

    response = client_user.get(f"/api/anexos/{anexo_id}")

    assert response.status_code == 200
    assert response.data == _PNG_BYTES
    # binário cru — NÃO é envelope JSON
    assert response.mimetype != "application/json"


def test_api_anexo_download_requires_session(client, seed_data):
    response = client.get("/api/anexos/999999")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_anexo_download_unknown_is_404_envelope(client_user):
    response = client_user.get("/api/anexos/999999")

    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_api_anexo_download_out_of_scope_is_403(
    client_outsider, seed_data, client_user
):
    """Anexo de tarefa fora do escopo do usuário => 403 envelopado."""
    task_id = seed_data["task_id"]
    upload = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(_PNG_BYTES), "img.png")},
        content_type="multipart/form-data",
    )
    anexo_id = _assert_ok_envelope(upload.get_json())["anexo"]["id"]

    response = client_outsider.get(f"/api/anexos/{anexo_id}")

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


def test_api_anexo_delete_author_succeeds(client_user, seed_data):
    task_id = seed_data["task_id"]
    upload = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(_PNG_BYTES), "del.png")},
        content_type="multipart/form-data",
    )
    anexo_id = _assert_ok_envelope(upload.get_json())["anexo"]["id"]

    response = client_user.post(f"/api/anexos/{anexo_id}/delete")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["anexo_id"] == anexo_id
    assert data["count"] == 0


def test_api_anexo_delete_non_author_is_403(client_editable, seed_data, client_user):
    """Usuário do mesmo órgão (vê a tarefa) mas NÃO autor não exclui anexo => 403."""
    task_id = seed_data["task_id"]
    upload = client_user.post(
        f"/api/tarefas/{task_id}/anexos",
        data={"file": (io.BytesIO(_PNG_BYTES), "x.png")},
        content_type="multipart/form-data",
    )
    anexo_id = _assert_ok_envelope(upload.get_json())["anexo"]["id"]

    response = client_editable.post(f"/api/anexos/{anexo_id}/delete")

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")
