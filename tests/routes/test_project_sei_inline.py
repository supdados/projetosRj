"""Contrato de múltiplos processos SEI via ``POST /api/projetos/<id>/inline``.

Fixa o requisito de produto: a SPA envia ``sei_processes`` (lista, substituição
completa); colar um número JÁ com o prefixo "SEI-" não é erro (normaliza); a
chave escalar ``sei_process`` segue aceita por 1 release (bundle cacheado); o
serializer devolve a lista E o escalar compat (primeiro número); mudanças caem
no histórico do projeto.
"""

from __future__ import annotations

from typing import Any

from models import ProjectHistory, ProjectSeiProcess, db


def _ok_data(payload: Any) -> dict[str, Any]:
    assert payload["ok"] is True
    return payload["data"]


def _fail_message(payload: Any) -> str:
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation"
    return payload["error"]["message"]


def _post_inline(client_user, project_id: int, body: dict):
    return client_user.post(f"/api/projetos/{project_id}/inline", json=body)


def test_inline_saves_list_and_returns_ordered_numbers(client_user, seed_data):
    response = _post_inline(
        client_user,
        seed_data["project_id"],
        {"sei_processes": ["380001/000664/2026", "SEI-380002/000001/2026"]},
    )

    assert response.status_code == 200
    project = _ok_data(response.get_json())["project"]
    assert project["sei_processes"] == [
        "SEI-380001/000664/2026",
        "SEI-380002/000001/2026",
    ]
    assert project["sei_process"] == "SEI-380001/000664/2026"


def test_inline_pasted_prefix_is_normalized_without_error(client_user, seed_data):
    response = _post_inline(
        client_user,
        seed_data["project_id"],
        {"sei_processes": ["sei- 380001/000664/2026"]},
    )

    assert response.status_code == 200
    project = _ok_data(response.get_json())["project"]
    assert project["sei_processes"] == ["SEI-380001/000664/2026"]


def test_inline_empty_list_clears_processes(client_user, seed_data):
    _post_inline(
        client_user, seed_data["project_id"], {"sei_processes": ["000001/2026"]}
    )

    response = _post_inline(client_user, seed_data["project_id"], {"sei_processes": []})

    assert response.status_code == 200
    project = _ok_data(response.get_json())["project"]
    assert project["sei_processes"] == []
    assert project["sei_process"] is None


def test_inline_non_list_payload_returns_422(client_user, seed_data):
    response = _post_inline(
        client_user, seed_data["project_id"], {"sei_processes": "000001/2026"}
    )

    assert response.status_code == 422
    assert "lista" in _fail_message(response.get_json())


def test_inline_oversized_number_returns_422(client_user, seed_data):
    response = _post_inline(
        client_user, seed_data["project_id"], {"sei_processes": ["9" * 60]}
    )

    assert response.status_code == 422
    assert "excede" in _fail_message(response.get_json())


def test_inline_too_many_numbers_returns_422(client_user, seed_data):
    numbers = [f"{380000 + n:06d}/000001/2026" for n in range(21)]
    response = _post_inline(
        client_user, seed_data["project_id"], {"sei_processes": numbers}
    )

    assert response.status_code == 422
    assert "Máximo" in _fail_message(response.get_json())


def test_inline_legacy_scalar_key_still_works(client_user, seed_data):
    response = _post_inline(
        client_user, seed_data["project_id"], {"sei_process": "380001/000664/2026"}
    )

    assert response.status_code == 200
    project = _ok_data(response.get_json())["project"]
    assert project["sei_processes"] == ["SEI-380001/000664/2026"]


def test_inline_legacy_scalar_edits_first_and_preserves_tail(client_user, seed_data):
    """Regressão: o bundle antigo só enxerga o primeiro número — editar por ele
    NÃO pode apagar os números 2..N adicionados pela SPA nova."""
    project_id = seed_data["project_id"]
    _post_inline(
        client_user,
        project_id,
        {"sei_processes": ["000001/2026", "000002/2026", "000003/2026"]},
    )

    response = _post_inline(client_user, project_id, {"sei_process": "999999/2026"})

    assert response.status_code == 200
    project = _ok_data(response.get_json())["project"]
    assert project["sei_processes"] == [
        "SEI-999999/2026",
        "SEI-000002/2026",
        "SEI-000003/2026",
    ]


def test_inline_change_is_recorded_in_history_and_noop_is_not(
    app, client_user, seed_data
):
    project_id = seed_data["project_id"]

    _post_inline(client_user, project_id, {"sei_processes": ["000001/2026"]})
    _post_inline(client_user, project_id, {"sei_processes": ["SEI-000001/2026"]})

    with app.app_context():
        entries = [
            h.action_description
            for h in ProjectHistory.query.filter_by(project_id=project_id)
            if "processos SEI" in h.action_description
        ]
        assert len(entries) == 1
        assert 'de "vazio" para "SEI-000001/2026"' in entries[0]


def test_creation_accepts_sei_processes_list(app, client_user, seed_data):
    response = client_user.post(
        "/api/projetos",
        json={
            "titulo": "Projeto Multi SEI",
            "orgao_id": seed_data["auditoria_orgao_id"],
            "sei_processes": ["380001/000664/2026", "SEI-380001/000665/2026"],
        },
    )

    assert response.status_code == 200
    project_id = _ok_data(response.get_json())["id"]
    with app.app_context():
        numbers = [
            item.numero
            for item in ProjectSeiProcess.query.filter_by(project_id=project_id)
            .order_by(ProjectSeiProcess.ordem)
            .all()
        ]
        assert numbers == ["SEI-380001/000664/2026", "SEI-380001/000665/2026"]


def test_creation_rejects_too_many_numbers(client_user, seed_data):
    numbers = [f"{380000 + n:06d}/000001/2026" for n in range(21)]
    response = client_user.post(
        "/api/projetos",
        json={
            "titulo": "Projeto SEI Estourado",
            "orgao_id": seed_data["auditoria_orgao_id"],
            "sei_processes": numbers,
        },
    )

    assert response.status_code == 422
    assert "Máximo" in _fail_message(response.get_json())


def test_creation_accepts_legacy_scalar_alias(app, client_user, seed_data):
    response = client_user.post(
        "/api/projetos",
        json={
            "titulo": "Projeto SEI Escalar",
            "orgao_id": seed_data["auditoria_orgao_id"],
            "sei_process": "380001/000664/2026",
        },
    )

    assert response.status_code == 200
    project_id = _ok_data(response.get_json())["id"]
    with app.app_context():
        numbers = [
            item.numero
            for item in ProjectSeiProcess.query.filter_by(project_id=project_id).all()
        ]
        assert numbers == ["SEI-380001/000664/2026"]
