"""Contrato do endpoint de importação de projetos via CSV da SPA.

Cobre ``POST /api/projetos/importar-csv`` (``routes/api/projects_import.py``):
guard de admin, validações 422 (sem órgão / sem arquivo / CSV inválido /
``mapeamento`` inválido), o caminho feliz legado (cabeçalho ``titulo``/
``descricao``) e o caminho com ``mapeamento`` de colunas.
"""

from __future__ import annotations

import io
import json

from models import Project
from services.sei_process import SEI_MAX_PER_PROJECT

_CSV_MAPEADO = (
    "Descrição;Observações;Título do Projeto;Situação;Processo SEI\n"
    "desc A;obs A;Projeto Mapeado 1;finalizado;"
    "SEI-380001/000664/2026,SEI-380001/000665/2026\n"
    "desc B;;Projeto Mapeado 2;planejando;\n"
    ";;;;\n"
)
_MAPEAMENTO_COMPLETO = {
    "2": "titulo",
    "0": "descricao",
    "1": "observacao",
    "3": "status",
    "4": "sei",
}


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
            **_csv(
                "titulo;descricao\nProjeto CSV 1;desc 1\nProjeto CSV 2;desc 2\n;sem titulo"
            ),
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


def test_import_com_mapeamento_cria_projetos(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "status": "Vigente",
            "mapeamento": json.dumps(_MAPEAMENTO_COMPLETO),
            **_csv(_CSV_MAPEADO),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["imported_count"] == 2
    assert data["ignored_count"] == 1
    assert data["adjusted_count"] == 1

    with app.app_context():
        primeiro = Project.query.filter_by(titulo="Projeto Mapeado 1").one()
        assert primeiro.short_description == "desc A"
        assert primeiro.observacao == "obs A"
        assert primeiro.status == "Finalizado"
        assert [item.numero for item in primeiro.sei_processes] == [
            "SEI-380001/000664/2026",
            "SEI-380001/000665/2026",
        ]


def test_import_mapeamento_status_invalido_cai_no_padrao(app, client_admin, seed_data):
    client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "status": "Suspenso",
            "mapeamento": json.dumps(_MAPEAMENTO_COMPLETO),
            **_csv(_CSV_MAPEADO),
        },
        content_type="multipart/form-data",
    )
    with app.app_context():
        segundo = Project.query.filter_by(titulo="Projeto Mapeado 2").one()
        assert segundo.status == "Suspenso"


def test_import_mapeamento_sem_titulo_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"0": "descricao"}),
            **_csv(_CSV_MAPEADO),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    payload = response.get_json()["error"]
    assert payload["code"] == "validation"
    assert payload["message"] == "Mapeie a coluna do título antes de importar."


def test_import_mapeamento_campo_invalido_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"2": "titulo", "3": "prioridade"}),
            **_csv(_CSV_MAPEADO),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    payload = response.get_json()["error"]
    assert payload["code"] == "validation"
    assert payload["message"].startswith(
        "Campo inválido no mapeamento: 'prioridade'. Use um de "
    )


def test_import_mapeamento_json_invalido_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": "nao-e-json",
            **_csv(_CSV_MAPEADO),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["message"].startswith("Mapeamento inválido: ")


def test_import_arquivo_acima_de_2_mb_422(client_admin, seed_data):
    gordo = {"arquivo": (io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "gordo.csv")}
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={"orgao_id": str(seed_data["auditoria_orgao_id"]), **gordo},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"].startswith("Arquivo acima de 2 MB")


def test_import_acima_de_10000_linhas_422(app, client_admin, seed_data):
    linhas = "\n".join(f"Projeto Teto {i};desc" for i in range(10_001))
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            **_csv(f"titulo;descricao\n{linhas}"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"] == "Importação acima de 10.000 projetos — divida o arquivo."

    with app.app_context():
        assert Project.query.filter_by(titulo="Projeto Teto 0").first() is None


def test_import_trunca_sei_no_teto_por_projeto(app, client_admin, seed_data):
    numeros = ",".join(f"380001/{i:06d}/2026" for i in range(SEI_MAX_PER_PROJECT + 5))
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"0": "titulo", "1": "sei"}),
            **_csv(f'Título;Processos\nProjeto SEI Teto;"{numeros}"'),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["imported_count"] == 1
    assert data["adjusted_count"] == 1

    with app.app_context():
        projeto = Project.query.filter_by(titulo="Projeto SEI Teto").one()
        assert len(projeto.sei_processes) == SEI_MAX_PER_PROJECT
        assert projeto.sei_processes[0].numero == "SEI-380001/000000/2026"


def test_import_campo_gigante_422(client_admin, seed_data):
    gigante = {
        "arquivo": (
            io.BytesIO(b"titulo;descricao\n" + b"a" * 200_000 + b";x\n"),
            "projetos.csv",
        )
    }
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={"orgao_id": str(seed_data["auditoria_orgao_id"]), **gigante},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"].startswith("Falha ao ler o CSV: CSV malformado")


def test_import_primeira_linha_do_excel_vazia_nao_vira_cabecalho(
    app, client_admin, seed_data
):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            **_csv(",,\ntitulo,descricao\nProjeto Excel Vazio,desc\n"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["imported_count"] == 1

    with app.app_context():
        assert Project.query.filter_by(titulo="Projeto Excel Vazio").one()
