"""Contrato do endpoint de importação de projetos via CSV da SPA.

Cobre ``POST /api/projetos/importar-csv`` (``routes/api/projects_import.py``):
guard de admin, validações 422 (sem órgão / sem arquivo / CSV inválido) e o
caminho feliz (cria um ``Project`` por linha com os atributos comuns).
"""

from __future__ import annotations

import io

from models import Project


def _csv(content: str):
    return {"arquivo": (io.BytesIO(content.encode("utf-8")), "projetos.csv")}


def test_import_requires_admin(client_user, seed_data):
    response = client_user.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            **_csv("titulo;descricao\nA;desc"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_import_without_orgao_returns_422(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data=_csv("titulo;descricao\nA;desc"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"


def test_import_without_file_returns_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={"orgao_id": str(seed_data["auditoria_orgao_id"])},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422


def test_import_invalid_header_returns_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            **_csv("nome;detalhe\nA;desc"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422


def test_import_creates_one_project_per_row(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "status": "Vigente",
            **_csv("titulo;descricao\nProjeto CSV 1;desc 1\nProjeto CSV 2;desc 2\n;sem titulo"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    # Linha sem título é ignorada → 2 projetos.
    assert data["imported_count"] == 2

    with app.app_context():
        criados = Project.query.filter(
            Project.titulo.in_(["Projeto CSV 1", "Projeto CSV 2"])
        ).all()
        assert {p.titulo for p in criados} == {"Projeto CSV 1", "Projeto CSV 2"}
        assert all(p.orgao_id == seed_data["auditoria_orgao_id"] for p in criados)


def test_import_returns_401_when_unauthenticated(client, seed_data):
    response = client.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            **_csv("titulo;descricao\nA;desc"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 401
