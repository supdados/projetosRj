"""Testes unitários do registry de colunas do export (services/project_export.py)."""

import datetime

import pytest

from models import (
    Etapa,
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
    EXPORT_COLUMNS,
    build_export_rows,
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
    assert len(EXPORT_COLUMNS) == 17
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
    assert valores["orgao"] == "SETD"
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
    assert len(DEFAULT_EXPORT_SLUGS) == 13
    assert set(DEFAULT_EXPORT_SLUGS) <= set(EXPORT_COLUMNS)
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
