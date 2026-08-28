"""Contrato do endpoint de importação de projetos via CSV da SPA.

Cobre ``POST /api/projetos/importar-csv`` (``routes/api/projects_import.py``):
guard de admin, validações 422 (sem órgão / sem arquivo / CSV inválido /
``mapeamento`` inválido), o caminho feliz legado (cabeçalho ``titulo``/
``descricao``) e o caminho com ``mapeamento`` de colunas.
"""

from __future__ import annotations

import io
import json
from datetime import date

from models import Etapa, Project
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
    assert data["etapas_criadas"] == 2

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
            "mapeamento": json.dumps({"2": "titulo", "3": "dono"}),
            **_csv(_CSV_MAPEADO),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    payload = response.get_json()["error"]
    assert payload["code"] == "validation"
    assert payload["message"].startswith(
        "Campo inválido no mapeamento: 'dono'. Use um de "
    )


def test_import_campo_de_etapa_no_modo_simples_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"0": "titulo", "1": "etapa"}),
            **_csv(_CSV_MAPEADO),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    payload = response.get_json()["error"]
    assert payload["code"] == "validation"
    assert payload["message"].startswith(
        "Campo 'etapa' não está disponível no modo 'simples'."
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


def _etapas_de(titulo: str) -> list[Etapa]:
    projeto = Project.query.filter_by(titulo=titulo).one()
    return Etapa.query.filter_by(project_id=projeto.id).order_by(Etapa.ordem).all()


def test_import_cria_etapa_default_em_todo_projeto(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            **_csv("titulo;descricao\nProjeto Etapa Default;desc"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["etapas_criadas"] == 1

    with app.app_context():
        (etapa,) = _etapas_de("Projeto Etapa Default")
        assert etapa.descricao == "Etapas a definir"
        assert (etapa.ordem, etapa.iniciada, etapa.done) == (0, False, False)
        assert (etapa.data_inicio, etapa.data_fim) == (None, None)


def test_import_etapa_default_recebe_as_datas_da_linha(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps(
                {"0": "titulo", "1": "data_inicio", "2": "data_fim"}
            ),
            **_csv(
                "Título;Início;Fim\nProjeto Com Datas;01/02/2026;2026-03-31\n"
                "Projeto Data Ilegivel;quando der;\n"
            ),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["etapas_criadas"] == 2
    # Só a linha com data ilegível conta como ajustada.
    assert data["adjusted_count"] == 1

    with app.app_context():
        (com_datas,) = _etapas_de("Projeto Com Datas")
        assert com_datas.data_inicio == date(2026, 2, 1)
        assert com_datas.data_fim == date(2026, 3, 31)
        (ilegivel,) = _etapas_de("Projeto Data Ilegivel")
        assert (ilegivel.data_inicio, ilegivel.data_fim) == (None, None)


def test_import_prioridade_por_linha(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"0": "titulo", "1": "prioridade"}),
            **_csv(
                "Título;Prioridade\nProjeto Prio OK;MÉDIA\n"
                "Projeto Prio Ruim;altíssima\nProjeto Prio Vazia;\n"
            ),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["adjusted_count"] == 1

    with app.app_context():
        prioridades = {
            titulo: Project.query.filter_by(titulo=titulo).one().prioridade
            for titulo in ("Projeto Prio OK", "Projeto Prio Ruim", "Projeto Prio Vazia")
        }
    assert prioridades == {
        "Projeto Prio OK": "media",
        "Projeto Prio Ruim": None,
        "Projeto Prio Vazia": None,
    }


def test_import_area_da_linha_vence_a_do_lote(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"0": "titulo", "1": "area"}),
            **_csv(
                "Título;Área responsável\nProjeto Area Conhecida;vpd\n"
                "Projeto Area Desconhecida;XPTO\nProjeto Area Vazia;\n"
            ),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    # Só a sigla desconhecida conta como ajuste.
    assert response.get_json()["data"]["adjusted_count"] == 1

    with app.app_context():
        conhecida = Project.query.filter_by(titulo="Projeto Area Conhecida").one()
        assert conhecida.orgao_id == seed_data["vpd_orgao_id"]
        for titulo in ("Projeto Area Desconhecida", "Projeto Area Vazia"):
            projeto = Project.query.filter_by(titulo=titulo).one()
            assert projeto.orgao_id == seed_data["auditoria_orgao_id"]


def test_import_orgao_e_area_sao_independentes(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"0": "titulo", "1": "orgao", "2": "area"}),
            **_csv(
                "Título;Órgão;Área responsável\n"
                "Projeto Orgao Livre;Secretaria de Fazenda;vpd\n"
                "Projeto Sem Orgao;;vpd\n"
            ),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200

    with app.app_context():
        livre = Project.query.filter_by(titulo="Projeto Orgao Livre").one()
        assert livre.orgao == "Secretaria de Fazenda"
        assert livre.orgao_id == seed_data["vpd_orgao_id"]
        # Mudança intencional: `orgao` não recebe mais a sigla da área.
        sem_orgao = Project.query.filter_by(titulo="Projeto Sem Orgao").one()
        assert sem_orgao.orgao is None


def test_import_orgao_truncado_em_100_caracteres(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "mapeamento": json.dumps({"0": "titulo", "1": "orgao"}),
            **_csv(f"Título;Órgão\nProjeto Orgao Longo;{'a' * 150}\n"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200

    with app.app_context():
        projeto = Project.query.filter_by(titulo="Projeto Orgao Longo").one()
        assert projeto.orgao == "a" * 100


_CSV_COM_ETAPAS = (
    "Ref Projeto;Título;Área responsável;Etapa;Etapa Data de início;"
    "Etapa Data de fim;Etapa Responsável;Etapa Situação;Etapa Comentários\n"
    "p1;Projeto Etapas 1;vpd;Levantamento;01/02/2026;2026-02-28;vpd;concluída;Kickoff\n"
    "p1;;;Execução;;;vpd, XPTO;em andamento;\n"
    "p1;;;Entrega;;;;;\n"
    "p2;Projeto Etapas 2;;Planejamento;;;;;\n"
    "p2;;;Homologação;;;;sim;\n"
)
_MAPEAMENTO_COM_ETAPAS = {
    "0": "ref_projeto",
    "1": "titulo",
    "2": "area",
    "3": "etapa",
    "4": "etapa_data_inicio",
    "5": "etapa_data_fim",
    "6": "etapa_responsavel",
    "7": "etapa_situacao",
    "8": "etapa_comentarios",
}


def _post_com_etapas(client_admin, seed_data, conteudo: str, mapeamento: dict):
    return client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "modo": "com_etapas",
            "mapeamento": json.dumps(mapeamento),
            **_csv(conteudo),
        },
        content_type="multipart/form-data",
    )


def test_import_com_etapas_cria_projetos_e_etapas(app, client_admin, seed_data):
    response = _post_com_etapas(
        client_admin, seed_data, _CSV_COM_ETAPAS, _MAPEAMENTO_COM_ETAPAS
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    # Só a linha com a sigla XPTO (desconhecida) conta como ajustada.
    assert data == {
        "imported_count": 2,
        "ignored_count": 0,
        "adjusted_count": 1,
        "etapas_criadas": 5,
    }

    with app.app_context():
        primeiro = Project.query.filter_by(titulo="Projeto Etapas 1").one()
        assert primeiro.orgao_id == seed_data["vpd_orgao_id"]
        etapas = _etapas_de("Projeto Etapas 1")
        assert [(e.descricao, e.ordem) for e in etapas] == [
            ("Levantamento", 0),
            ("Execução", 1),
            ("Entrega", 2),
        ]
        levantamento, execucao, entrega = etapas
        assert (levantamento.iniciada, levantamento.done) == (True, True)
        assert levantamento.data_inicio == date(2026, 2, 1)
        assert levantamento.data_fim == date(2026, 2, 28)
        assert levantamento.comentarios == "Kickoff"
        assert [r.area_id for r in levantamento.responsaveis] == [
            seed_data["vpd_orgao_id"]
        ]
        assert (execucao.iniciada, execucao.done) == (True, False)
        assert [(r.area_id, r.label) for r in execucao.responsaveis] == [
            (seed_data["vpd_orgao_id"], "vpd"),
            (None, "Outras áreas"),
        ]
        assert (entrega.iniciada, entrega.done) == (False, False)


def test_import_com_etapas_herda_projeto_da_primeira_linha(
    app, client_admin, seed_data
):
    response = _post_com_etapas(
        client_admin, seed_data, _CSV_COM_ETAPAS, _MAPEAMENTO_COM_ETAPAS
    )
    assert response.status_code == 200

    with app.app_context():
        segundo = Project.query.filter_by(titulo="Projeto Etapas 2").one()
        assert segundo.orgao_id == seed_data["auditoria_orgao_id"]
        planejamento, homologacao = _etapas_de("Projeto Etapas 2")
        assert (planejamento.iniciada, planejamento.done) == (False, False)
        assert (homologacao.iniciada, homologacao.done) == (True, True)


def test_import_com_etapas_ref_nao_contigua_422(app, client_admin, seed_data):
    reordenado = (
        "Ref Projeto;Título;Etapa\n" "p1;Projeto A;E1\n" "p2;Projeto B;E1\n" "p1;;E2\n"
    )
    response = _post_com_etapas(
        client_admin,
        seed_data,
        reordenado,
        {"0": "ref_projeto", "1": "titulo", "2": "etapa"},
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"] == (
        "Linha 4: linhas do projeto 'p1' não são contíguas — "
        "a planilha foi reordenada?"
    )

    with app.app_context():
        assert Project.query.filter_by(titulo="Projeto A").first() is None


def test_import_com_etapas_sem_mapeamento_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "modo": "com_etapas",
            **_csv(_CSV_COM_ETAPAS),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "validation"
    assert error["message"].startswith("O modo com etapas exige o mapeamento")


def test_import_com_etapas_mapeamento_sem_ref_e_etapa_422(client_admin, seed_data):
    sem_ref = _post_com_etapas(
        client_admin, seed_data, _CSV_COM_ETAPAS, {"1": "titulo", "3": "etapa"}
    )
    assert sem_ref.status_code == 422
    assert sem_ref.get_json()["error"]["message"] == (
        "Mapeie a coluna da referência do projeto (Ref do projeto) "
        "no modo com etapas."
    )

    sem_etapa = _post_com_etapas(
        client_admin, seed_data, _CSV_COM_ETAPAS, {"0": "ref_projeto", "1": "titulo"}
    )
    assert sem_etapa.status_code == 422
    assert sem_etapa.get_json()["error"]["message"] == (
        "Mapeie a coluna da etapa no modo com etapas."
    )


def test_import_modo_desconhecido_422(client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "modo": "turbo",
            **_csv("titulo;descricao\nA;desc"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["message"].startswith("Modo inválido: 'turbo'")


def test_import_modo_simples_explicito_e_o_padrao(app, client_admin, seed_data):
    response = client_admin.post(
        "/api/projetos/importar-csv",
        data={
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "modo": "simples",
            **_csv("titulo;descricao\nProjeto Modo Simples;desc"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["etapas_criadas"] == 1
