"""Testes unitários do registry de colunas do export (services/project_export.py)."""

import datetime

import pytest

from models import (
    Etapa,
    EtapaResponsavel,
    Indicador,
    IndicadorProjeto,
    Objetivo,
    OrgaoUnidade,
    Project,
    ProjectSeiProcess,
    ResultadoEsperado,
)
from services.project_export import (
    DEFAULT_EXPORT_SLUGS,
    DEFAULT_EXPORT_STAGE_SLUGS,
    EXPORT_COLUMNS,
    EXPORT_STAGE_COLUMNS,
    build_export_headers_with_stages,
    build_export_rows,
    build_export_rows_with_stages,
    write_tabular_bytes,
)


def _projeto_minimo() -> Project:
    projeto = Project(titulo="Projeto Mínimo")
    projeto.id = 7
    return projeto


def _projeto_completo() -> Project:
    projeto = Project(
        titulo="Portal Único",
        short_description="Descrição longa",
        status="Vigente",
        prioridade="alta",
        delivery_type="Sistema",
        special_project="ABEP",
        observacao="Observação geral",
        orgao="Secretaria de Estado de Transformação Digital",
        orgao_ref=OrgaoUnidade(sigla="SETD", nome="SETD", tipo="Secretaria"),
        objetivo=Objetivo(descricao="Objetivo X"),
        resultado_esperado=ResultadoEsperado(descricao="Resultado Y"),
        indicadores=[IndicadorProjeto(indicador=Indicador(descricao="Indicador Z"))],
        sei_processes=[
            ProjectSeiProcess(numero="SEI-380001/000664/2026", ordem=0),
            ProjectSeiProcess(numero="SEI-380001/000665/2026", ordem=1),
        ],
        etapas=[
            Etapa(
                descricao="Planejamento",
                iniciada=True,
                done=True,
                data_inicio=datetime.date(2026, 1, 10),
                data_fim=datetime.date(2026, 1, 15),
                ordem=0,
            ),
            Etapa(
                descricao="Execução",
                iniciada=False,
                done=False,
                data_inicio=datetime.date(2026, 2, 1),
                data_fim=datetime.date(2026, 2, 5),
                ordem=1,
            ),
        ],
    )
    projeto.id = 1
    return projeto


def test_todos_slugs_renderizam():
    assert len(EXPORT_COLUMNS) == 18
    minimo = _projeto_minimo()
    completo = _projeto_completo()
    for column in EXPORT_COLUMNS.values():
        assert isinstance(column.render(minimo), str)
        assert isinstance(column.render(completo), str)


def test_projeto_minimo_valores():
    valores = {
        slug: column.render(_projeto_minimo())
        for slug, column in EXPORT_COLUMNS.items()
    }
    assert valores["id"] == "7"
    assert valores["titulo"] == "Projeto Mínimo"
    assert valores["descricao"] == ""
    assert valores["area"] == ""
    assert valores["orgao"] == ""
    assert valores["data_inicio"] == ""
    assert valores["data_fim"] == ""
    assert valores["total_etapas"] == "0"
    assert valores["cumprimento"] == "0%"


def test_projeto_completo_valores():
    valores = {
        slug: column.render(_projeto_completo())
        for slug, column in EXPORT_COLUMNS.items()
    }
    assert valores["sei"] == "SEI-380001/000664/2026; SEI-380001/000665/2026"
    assert valores["area"] == "SETD"
    assert valores["orgao"] == "Secretaria de Estado de Transformação Digital"
    assert valores["prioridade"] == "alta"
    assert valores["data_inicio"] == "10/01/2026"
    assert valores["data_fim"] == "05/02/2026"
    assert valores["objetivo"] == "Objetivo X"
    assert valores["resultado"] == "Resultado Y"
    assert valores["indicadores"] == "Indicador Z"
    assert valores["tipo_entrega"] == "Sistema"
    assert valores["projeto_especial"] == "ABEP"
    assert valores["observacao"] == "Observação geral"
    assert valores["total_etapas"] == "2"
    assert valores["cumprimento"] == "50%"


def test_render_neutraliza_formulas():
    projeto = _projeto_minimo()
    projeto.titulo = '=HYPERLINK("https://attacker.example","x")'
    assert EXPORT_COLUMNS["titulo"].render(projeto).startswith("'=")


def test_default_slugs_sao_o_preset_legado():
    assert len(DEFAULT_EXPORT_SLUGS) == 14
    assert set(DEFAULT_EXPORT_SLUGS) <= set(EXPORT_COLUMNS)
    assert DEFAULT_EXPORT_SLUGS.index("area") < DEFAULT_EXPORT_SLUGS.index("orgao")
    assert set(EXPORT_COLUMNS) - set(DEFAULT_EXPORT_SLUGS) == {
        "prioridade",
        "tipo_entrega",
        "projeto_especial",
        "observacao",
    }


def test_build_export_rows_segue_a_ordem_pedida():
    rows = list(build_export_rows([_projeto_completo()], ["titulo", "id"]))
    assert rows == [["Portal Único", "1"]]


def test_write_tabular_bytes_csv_com_bom_e_quote_all():
    raw = write_tabular_bytes(["A", "B"], [["1", "x;y"]])
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig") == '"A";"B"\r\n"1";"x;y"\r\n'


def test_write_tabular_bytes_formato_desconhecido():
    with pytest.raises(ValueError, match="Formato de arquivo não suportado"):
        write_tabular_bytes(["A"], [], "xlsx")


def _etapa_responsavel(sigla: str) -> EtapaResponsavel:
    item = EtapaResponsavel(label=sigla, ordem=0)
    item.area = OrgaoUnidade(sigla=sigla, nome=sigla, tipo="Subsecretaria")
    return item


def _projeto_com_etapas() -> Project:
    projeto = Project(
        titulo="Portal Único",
        orgao="Secretaria de Estado de Transformação Digital",
        orgao_ref=OrgaoUnidade(sigla="SETD", nome="SETD", tipo="Secretaria"),
        etapas=[
            Etapa(
                descricao="Planejamento",
                iniciada=True,
                done=True,
                data_inicio=datetime.date(2026, 1, 10),
                data_fim=datetime.date(2026, 1, 15),
                comentarios="Ata publicada",
                ordem=0,
                responsaveis=[_etapa_responsavel("SUBEXE")],
            ),
            Etapa(descricao="Execução", iniciada=False, done=False, ordem=1),
        ],
    )
    projeto.id = 12
    return projeto


def test_stage_columns_registry_ordem_e_cabecalhos():
    assert [(slug, column.header) for slug, column in EXPORT_STAGE_COLUMNS.items()] == [
        ("etapa", "Etapa"),
        ("etapa_data_inicio", "Etapa Data de início"),
        ("etapa_data_fim", "Etapa Data de fim"),
        ("etapa_responsavel", "Etapa Responsável"),
        ("etapa_situacao", "Etapa Situação"),
        ("etapa_comentarios", "Etapa Comentários"),
    ]


def test_default_stage_slugs_sao_todos():
    assert DEFAULT_EXPORT_STAGE_SLUGS == tuple(EXPORT_STAGE_COLUMNS)


def test_stage_situacao_por_estado():
    render = EXPORT_STAGE_COLUMNS["etapa_situacao"].render
    assert render(Etapa(descricao="a", iniciada=True, done=True)) == "Concluída"
    assert render(Etapa(descricao="b", iniciada=True, done=False)) == "Em andamento"
    assert render(Etapa(descricao="c", iniciada=False, done=False)) == "Não iniciada"


def test_stage_responsavel_usa_a_relacao_n_a_n():
    etapa = Etapa(
        descricao="Planejamento",
        responsaveis=[_etapa_responsavel("SUBEXE"), _etapa_responsavel("COODADOS")],
    )
    assert EXPORT_STAGE_COLUMNS["etapa_responsavel"].render(etapa) == "SUBEXE, COODADOS"


def test_stage_responsavel_cai_no_espelho_legado():
    etapa = Etapa(descricao="Planejamento", responsavel="SUBEXE")
    assert EXPORT_STAGE_COLUMNS["etapa_responsavel"].render(etapa) == "SUBEXE"


def test_stage_render_neutraliza_formula_em_comentarios():
    etapa = Etapa(descricao="Planejamento", comentarios="=1+1")
    assert EXPORT_STAGE_COLUMNS["etapa_comentarios"].render(etapa) == "'=1+1"


def test_stage_datas_vazias_viram_string_vazia():
    etapa = Etapa(descricao="Planejamento")
    assert EXPORT_STAGE_COLUMNS["etapa_data_inicio"].render(etapa) == ""
    assert EXPORT_STAGE_COLUMNS["etapa_data_fim"].render(etapa) == ""


def test_headers_with_stages_comeca_por_ref_projeto():
    cabecalhos = build_export_headers_with_stages(
        ["titulo", "area"], ["etapa", "etapa_situacao"]
    )
    assert cabecalhos == [
        "Ref Projeto",
        "Título",
        "Área responsável",
        "Etapa",
        "Etapa Situação",
    ]


def test_rows_with_stages_uma_linha_por_etapa():
    rows = list(
        build_export_rows_with_stages(
            [_projeto_com_etapas()],
            ["titulo"],
            ["etapa", "etapa_data_inicio", "etapa_responsavel", "etapa_situacao"],
        )
    )
    assert rows == [
        ["12", "Portal Único", "Planejamento", "10/01/2026", "SUBEXE", "Concluída"],
        ["12", "Portal Único", "Execução", "", "", "Não iniciada"],
    ]


def test_rows_with_stages_projeto_sem_etapa_vira_linha_unica():
    rows = list(
        build_export_rows_with_stages(
            [_projeto_minimo()], ["titulo"], ["etapa", "etapa_situacao"]
        )
    )
    assert rows == [["7", "Projeto Mínimo", "", ""]]


def test_rows_with_stages_ignora_reuniao_do_google():
    projeto = _projeto_com_etapas()
    projeto.etapas.append(
        Etapa(descricao="Reunião de alinhamento", entry_type="google_meeting", ordem=2)
    )
    descricoes = [
        row[-1]
        for row in build_export_rows_with_stages([projeto], ["titulo"], ["etapa"])
    ]
    assert descricoes == ["Planejamento", "Execução"]


def test_area_e_orgao_sao_colunas_independentes():
    projeto = _projeto_com_etapas()
    valores = {slug: EXPORT_COLUMNS[slug].render(projeto) for slug in ("area", "orgao")}
    assert valores["area"] == "SETD"
    assert valores["orgao"] == "Secretaria de Estado de Transformação Digital"
    projeto.orgao_ref = None
    assert EXPORT_COLUMNS["area"].render(projeto) == ""
    assert EXPORT_COLUMNS["orgao"].render(projeto) != ""
