"""Contrato do endpoint de exportação de projetos da SPA.

Cobre ``GET /api/projetos/exportar`` (``routes/api/projects_export.py``): guard
de login, preset de colunas com BOM/";", ordem custom de colunas, validações
422, escopo de visibilidade de não-admin, filtro de status sem default
implícito, teto de linhas, neutralização de fórmulas (CSV injection) e o
formato longo ``?com_etapas=1``.
"""

from __future__ import annotations

import csv
import io
import re

from models import Etapa, Project, db

STAGE_HEADERS = [
    "Etapa",
    "Etapa Data de início",
    "Etapa Data de fim",
    "Etapa Responsável",
    "Etapa Situação",
    "Etapa Comentários",
]

DEFAULT_HEADERS = [
    "ID",
    "Título",
    "Descrição",
    "Processos SEI",
    "Área responsável",
    "Órgão",
    "Status",
    "Data de início",
    "Data de fim",
    "Objetivo EEGD",
    "Resultado EEGD",
    "Indicadores EEGD",
    "Total de etapas",
    "Cumprimento (%)",
]


def _rows(response) -> list[list[str]]:
    text = response.get_data(as_text=True)
    return list(csv.reader(io.StringIO(text.lstrip("\ufeff")), delimiter=";"))


def test_export_requires_login(client):
    response = client.get("/api/projetos/exportar")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthenticated"


def test_export_default_200(client_user, seed_data):
    response = client_user.get("/api/projetos/exportar")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert re.fullmatch(
        r'attachment; filename="projetos-\d{8}-\d{4}\.csv"',
        response.headers["Content-Disposition"],
    )
    assert response.get_data().startswith(b"\xef\xbb\xbf")
    rows = _rows(response)
    assert rows[0] == DEFAULT_HEADERS
    titulos = [row[1] for row in rows[1:]]
    assert "Projeto Auditoria" in titulos


def test_export_colunas_custom_ordem(client_user, seed_data):
    response = client_user.get("/api/projetos/exportar?colunas=titulo,id")
    assert response.status_code == 200
    rows = _rows(response)
    assert rows[0] == ["Título", "ID"]
    linha = next(row for row in rows[1:] if row[0] == "Projeto Auditoria")
    assert linha[1] == str(seed_data["project_id"])


def test_export_slug_invalido_422(client_user, seed_data):
    response = client_user.get("/api/projetos/exportar?colunas=titulo,foo")
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert "Coluna inválida: 'foo'" in error["message"]


def test_export_colunas_vazio_422(client_user, seed_data):
    response = client_user.get("/api/projetos/exportar?colunas=")
    assert response.status_code == 422
    assert response.get_json()["error"]["message"] == "Escolha ao menos uma coluna."


def test_export_orgao_invalido_422(client_user, seed_data):
    response = client_user.get(
        f"/api/projetos/exportar?orgao={seed_data['vpd_orgao_id']}"
    )
    assert response.status_code == 422
    assert (
        response.get_json()["error"]["message"]
        == "Filtro de órgão inválido para o usuário."
    )


def test_export_escopo_nao_admin(client_user, client_admin, seed_data):
    corpo_user = client_user.get("/api/projetos/exportar?colunas=titulo").get_data(
        as_text=True
    )
    corpo_admin = client_admin.get("/api/projetos/exportar?colunas=titulo").get_data(
        as_text=True
    )
    assert "Projeto VPD" not in corpo_user
    assert "Projeto VPD" in corpo_admin


def test_export_filtro_status_sem_default_implicito(app, client_admin, seed_data):
    with app.app_context():
        auditoria_id = seed_data["auditoria_orgao_id"]
        db.session.add(
            Project(
                titulo="Projeto Encerrado Export",
                orgao_id=auditoria_id,
                status="Finalizado",
            )
        )
        db.session.commit()

    sem_filtro = _rows(client_admin.get("/api/projetos/exportar?colunas=titulo"))
    titulos_sem_filtro = [row[0] for row in sem_filtro[1:]]
    assert "Projeto Encerrado Export" in titulos_sem_filtro
    assert "Projeto Auditoria" in titulos_sem_filtro

    filtrado = _rows(
        client_admin.get("/api/projetos/exportar?colunas=titulo&status=Finalizado")
    )
    titulos_filtrados = [row[0] for row in filtrado[1:]]
    assert "Projeto Encerrado Export" in titulos_filtrados
    assert "Projeto Auditoria" not in titulos_filtrados


def test_export_teto_de_linhas_422(client_user, seed_data, monkeypatch):
    monkeypatch.setattr("routes.api.projects_export.MAX_EXPORT_ROWS", 0)
    response = client_user.get("/api/projetos/exportar")
    assert response.status_code == 422
    assert (
        response.get_json()["error"]["message"]
        == "Exportação acima de 10.000 projetos — refine os filtros."
    )


def test_export_neutraliza_formulas(app, client_admin, seed_data):
    with app.app_context():
        db.session.add(
            Project(
                titulo='=HYPERLINK("https://attacker.example","click")',
                orgao_id=seed_data["auditoria_orgao_id"],
                status="Vigente",
            )
        )
        db.session.commit()

    rows = _rows(client_admin.get("/api/projetos/exportar?colunas=titulo"))
    injetado = next(row for row in rows[1:] if "HYPERLINK" in row[0])
    assert injetado[0].startswith("'=")


def test_export_com_etapas_headers_e_ref_projeto(client_user, seed_data):
    response = client_user.get("/api/projetos/exportar?com_etapas=1&colunas=titulo")
    assert response.status_code == 200
    rows = _rows(response)
    assert rows[0] == ["Ref Projeto", "Título", *STAGE_HEADERS]
    linhas = [row for row in rows[1:] if row[1] == "Projeto Auditoria"]
    assert [row[0] for row in linhas] == [str(seed_data["project_id"])] * 2
    assert [row[2] for row in linhas] == ["Etapa Planejada", "Etapa Iniciada"]
    assert linhas[0][3] == "10/01/2026"
    assert linhas[0][5] == "Usuario Auditoria"
    assert [row[6] for row in linhas] == ["Não iniciada", "Em andamento"]


def test_export_com_etapas_projeto_sem_etapa_vira_linha_vazia(
    app, client_admin, seed_data
):
    with app.app_context():
        db.session.add(
            Project(
                titulo="Projeto Sem Etapa",
                orgao_id=seed_data["auditoria_orgao_id"],
                status="Vigente",
            )
        )
        db.session.commit()

    rows = _rows(client_admin.get("/api/projetos/exportar?com_etapas=1&colunas=titulo"))
    linhas = [row for row in rows[1:] if row[1] == "Projeto Sem Etapa"]
    assert len(linhas) == 1
    assert linhas[0][2:] == [""] * len(STAGE_HEADERS)


def test_export_com_etapas_colunas_etapa_custom_ordem(client_user, seed_data):
    response = client_user.get(
        "/api/projetos/exportar?com_etapas=1&colunas=titulo"
        "&colunas_etapa=etapa_situacao,etapa"
    )
    assert response.status_code == 200
    rows = _rows(response)
    assert rows[0] == ["Ref Projeto", "Título", "Etapa Situação", "Etapa"]


def test_export_colunas_etapa_invalida_422(client_user, seed_data):
    response = client_user.get(
        "/api/projetos/exportar?com_etapas=1&colunas_etapa=etapa,foo"
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert "Coluna inválida: 'foo'" in error["message"]


def test_export_colunas_etapa_vazio_422(client_user, seed_data):
    response = client_user.get("/api/projetos/exportar?com_etapas=1&colunas_etapa=")
    assert response.status_code == 422
    assert response.get_json()["error"]["message"] == "Escolha ao menos uma coluna."


def test_export_com_etapas_teto_conta_linhas(client_user, seed_data, monkeypatch):
    projetos = _rows(client_user.get("/api/projetos/exportar?colunas=titulo"))[1:]
    monkeypatch.setattr("routes.api.projects_export.MAX_EXPORT_ROWS", len(projetos))
    assert client_user.get("/api/projetos/exportar?colunas=titulo").status_code == 200

    response = client_user.get("/api/projetos/exportar?com_etapas=1&colunas=titulo")
    assert response.status_code == 422
    assert (
        response.get_json()["error"]["message"]
        == "Exportação acima de 10.000 linhas — refine os filtros."
    )


def test_export_com_etapas_neutraliza_formulas_em_comentarios(
    app, client_admin, seed_data
):
    with app.app_context():
        db.session.add(
            Etapa(
                descricao="Etapa Injetada",
                comentarios='=HYPERLINK("https://attacker.example","click")',
                project_id=seed_data["project_id"],
                ordem=9,
            )
        )
        db.session.commit()

    rows = _rows(client_admin.get("/api/projetos/exportar?com_etapas=1&colunas=titulo"))
    injetada = next(row for row in rows[1:] if row[2] == "Etapa Injetada")
    assert injetada[7].startswith("'=")


QUICK_HEADERS = [
    "ID",
    "Situação",
    "Objeto / Produto",
    "Localização",
    "Escopo",
    "Execução física e financeira",
    "Contratos e instrumentos",
    "Datas de início e fim previstas",
    "Próximas etapas e prazos",
    "Ponto crítico / Riscos",
    "Processo SEI",
    "TCE",
    "Responsável",
]


def _add_projeto(app, titulo: str, orgao_id: int, status: str) -> None:
    with app.app_context():
        db.session.add(Project(titulo=titulo, orgao_id=orgao_id, status=status))
        db.session.commit()


def test_export_rapida_colunas_fixas_e_todos_status(app, client_admin, seed_data):
    auditoria_id = seed_data["auditoria_orgao_id"]
    _add_projeto(app, "Projeto Finalizado Rápido", auditoria_id, "Finalizado")
    _add_projeto(app, "Projeto Suspenso Rápido", auditoria_id, "Suspenso")

    response = client_admin.get("/api/projetos/exportar?rapida=1")
    assert response.status_code == 200
    assert re.fullmatch(
        r'attachment; filename="projetos-rapida-\d{8}-\d{4}\.csv"',
        response.headers["Content-Disposition"],
    )
    rows = _rows(response)
    assert rows[0] == QUICK_HEADERS
    status_por_nome = {row[2]: row[1] for row in rows[1:]}
    assert status_por_nome["Projeto Auditoria"] == "Vigente"
    assert status_por_nome["Projeto Finalizado Rápido"] == "Concluído"
    assert status_por_nome["Projeto Suspenso Rápido"] == "Suspenso"


def test_export_rapida_campos_do_sistema_e_colunas_vazias(client_user, seed_data):
    rows = _rows(client_user.get("/api/projetos/exportar?rapida=1"))
    linha = dict(
        zip(QUICK_HEADERS, next(r for r in rows[1:] if r[2] == "Projeto Auditoria"))
    )
    assert linha["ID"] == str(seed_data["project_id"])
    assert linha["Localização"] == "Orgao A"
    assert linha["Execução física e financeira"] == "0/2 etapas"
    assert linha["Objeto / Produto"] == "Projeto Auditoria"
    assert linha["Datas de início e fim previstas"] == "10/01/2026 a 20/01/2026"
    assert linha["Próximas etapas e prazos"] == (
        "Etapa Planejada (10/01/2026 a 15/01/2026) — Usuario Auditoria"
    )
    assert linha["TCE"] == "Não"
    assert linha["Responsável"] == "Auditoria"
    vazias = ["Contratos e instrumentos", "Ponto crítico / Riscos"]
    assert [linha[coluna] for coluna in vazias] == ["", ""]


def test_export_rapida_filtra_so_por_area(app, client_admin, seed_data):
    auditoria_id = seed_data["auditoria_orgao_id"]
    _add_projeto(app, "Projeto Finalizado Rápido", auditoria_id, "Finalizado")

    response = client_admin.get(
        f"/api/projetos/exportar?rapida=1&orgao={auditoria_id}"
        "&status=Vigente&prioridade=alta&q=inexistente&colunas=foo"
    )
    assert response.status_code == 200
    nomes = [row[2] for row in _rows(response)[1:]]
    assert "Projeto Auditoria" in nomes
    assert "Projeto Finalizado Rápido" in nomes
    assert "Projeto VPD" not in nomes


def test_export_rapida_escopo_nao_admin(client_user, seed_data):
    corpo = client_user.get("/api/projetos/exportar?rapida=1").get_data(as_text=True)
    assert "Projeto Auditoria" in corpo
    assert "Projeto VPD" not in corpo


def test_export_rapida_orgao_invalido_422(client_user, seed_data):
    response = client_user.get(
        f"/api/projetos/exportar?rapida=1&orgao={seed_data['vpd_orgao_id']}"
    )
    assert response.status_code == 422


def test_export_rapida_teto_de_linhas_422(client_user, seed_data, monkeypatch):
    monkeypatch.setattr("routes.api.projects_export.MAX_EXPORT_ROWS", 0)
    response = client_user.get("/api/projetos/exportar?rapida=1")
    assert response.status_code == 422
    assert (
        response.get_json()["error"]["message"]
        == "Exportação acima de 10.000 projetos — refine os filtros."
    )
