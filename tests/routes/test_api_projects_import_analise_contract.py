"""Contrato do endpoint de análise do CSV de importação de projetos.

Cobre ``POST /api/projetos/importar-csv/analise``
(``routes/api/projects_import.py``): guard de admin, validações 422 (sem
arquivo / acima de 2 MB / ilegível) e o shape da sugestão de colunas.
"""

from __future__ import annotations

import io

import pytest


def _csv(content: str) -> dict[str, tuple[io.BytesIO, str]]:
    return {"arquivo": (io.BytesIO(content.encode("utf-8")), "projetos.csv")}


def test_analise_requires_admin(client, client_user):
    anon = client.post(
        "/api/projetos/importar-csv/analise",
        data=_csv("Título;Descrição\nA;desc"),
        content_type="multipart/form-data",
    )
    assert anon.status_code == 401

    usuario = client_user.post(
        "/api/projetos/importar-csv/analise",
        data=_csv("Título;Descrição\nA;desc"),
        content_type="multipart/form-data",
    )
    assert usuario.status_code == 403
    assert usuario.get_json()["error"]["code"] == "forbidden"


def test_analise_sem_arquivo_422(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data={},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"] == "Selecione um arquivo CSV para importar."


def test_analise_arquivo_grande_422(client_admin):
    gordo = {"arquivo": (io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "gordo.csv")}
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=gordo,
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["message"].startswith("Arquivo acima de 2 MB")


def test_analise_arquivo_vazio_422(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv("   \n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"].startswith("Falha ao ler o CSV: ")


def test_analise_sugere_colunas(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv(
            "Título do Projeto;Resumo;Dono\n"
            "Portal Único;Unifica os portais;Maria\n"
            "Painel EEGD;;João\n"
        ),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["delimitador"] == ";"
    assert data["total_linhas"] == 2
    assert data["colunas"] == [
        {
            "indice": 0,
            "cabecalho": "Título do Projeto",
            "campo": "titulo",
            "confianca": "sinonimo",
            "amostra": "Portal Único",
        },
        {
            "indice": 1,
            "cabecalho": "Resumo",
            "campo": "descricao",
            "confianca": "sinonimo",
            "amostra": "Unifica os portais",
        },
        {
            "indice": 2,
            "cabecalho": "Dono",
            "campo": None,
            "confianca": None,
            "amostra": "Maria",
        },
    ]
    assert data["campos"][0] == {
        "campo": "titulo",
        "rotulo": "Título",
        "obrigatorio": True,
    }
    assert [campo["campo"] for campo in data["campos"]] == [
        "titulo",
        "descricao",
        "status",
        "delivery_type",
        "special_project",
        "observacao",
        "sei",
    ]
    assert all(not campo["obrigatorio"] for campo in data["campos"][1:])


def test_analise_colunas_acentuadas_fora_de_ordem(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv(
            "Observações;SITUAÇÃO;Título;Processo SEI;Tipo de Entrega\n"
            ";Vigente;Portal;SEI-260002/000001/2026;Sistema\n"
        ),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    colunas = response.get_json()["data"]["colunas"]
    assert [coluna["campo"] for coluna in colunas] == [
        "observacao",
        "status",
        "titulo",
        "sei",
        "delivery_type",
    ]
    assert colunas[2]["confianca"] == "exato"
    assert colunas[0]["amostra"] == ""
    assert colunas[3]["amostra"] == "SEI-260002/000001/2026"


def test_analise_delimitador_virgula(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv("Título,Descrição\nPortal,Unifica\n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["delimitador"] == ","
    assert data["total_linhas"] == 1
    assert [coluna["cabecalho"] for coluna in data["colunas"]] == [
        "Título",
        "Descrição",
    ]


def test_analise_colunas_demais_422(client_admin):
    cabecalho = ";".join(f"coluna {indice}" for indice in range(201))
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv(f"{cabecalho}\n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"] == "Arquivo acima de 200 colunas (recebidas 201)."


def test_analise_limite_de_colunas_permite_200(client_admin):
    cabecalho = ";".join(f"coluna {indice}" for indice in range(200))
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv(f"{cabecalho}\n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert len(response.get_json()["data"]["colunas"]) == 200


def test_analise_delimitador_ignora_linha_em_branco_inicial(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv("\nTítulo,Descrição\nPortal,Unifica\n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["delimitador"] == ","
    assert [coluna["cabecalho"] for coluna in data["colunas"]] == [
        "Título",
        "Descrição",
    ]


def _csv_bytes(content: bytes) -> dict[str, tuple[io.BytesIO, str]]:
    return {"arquivo": (io.BytesIO(content), "projetos.csv")}


def _csv_de_tamanho(total_bytes: int) -> bytes:
    """CSV ASCII válido com exatamente ``total_bytes`` (campos abaixo do teto do csv)."""
    cabecalho = b"titulo;descricao\n"
    linha = b"Portal;desc\n"
    corpo = linha * ((total_bytes - len(cabecalho)) // len(linha))
    sobra = total_bytes - len(cabecalho) - len(corpo)
    return cabecalho + corpo[:-1] + b"x" * sobra + b"\n"


def test_analise_campo_gigante_422(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv_bytes(b"titulo;descricao\n" + b"a" * 200_000 + b";x\n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"].startswith("Falha ao ler o CSV: CSV malformado")


def test_analise_primeira_linha_do_excel_vazia_nao_vira_cabecalho(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv(",,\nTítulo,Descrição\nPortal,Unifica\n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total_linhas"] == 1
    assert [coluna["cabecalho"] for coluna in data["colunas"]] == [
        "Título",
        "Descrição",
    ]
    assert [coluna["campo"] for coluna in data["colunas"]] == ["titulo", "descricao"]


def test_analise_primeira_linha_so_de_espacos_nao_vira_cabecalho(client_admin):
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv("   \nTítulo,Descrição\nPortal,Unifica\n"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total_linhas"] == 1
    assert [coluna["cabecalho"] for coluna in data["colunas"]] == [
        "Título",
        "Descrição",
    ]


@pytest.mark.parametrize("tamanho", [2 * 1024 * 1024, 2 * 1024 * 1024 - 100])
def test_analise_arquivo_no_teto_de_2_mb_passa(client_admin, tamanho):
    conteudo = _csv_de_tamanho(tamanho)
    assert len(conteudo) == tamanho
    response = client_admin.post(
        "/api/projetos/importar-csv/analise",
        data=_csv_bytes(conteudo),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert [
        coluna["cabecalho"] for coluna in response.get_json()["data"]["colunas"]
    ] == ["titulo", "descricao"]
