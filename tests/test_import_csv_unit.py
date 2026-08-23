"""Testes unitários para routes/projects/import_csv.py.

``parse_import_rows`` recebe bytes crus e não depende de Flask/DB, portanto
todos os casos aqui são puros — cobrem detecção de encoding, separador,
cabeçalho ausente e filtragem de linhas sem título.
"""

import csv

import pytest

from routes.projects.import_csv import (
    ParsedImportRow,
    _filter_sei_numbers,
    _resolve_row_attributes,
    parse_import_rows,
    read_tabular_bytes,
)
from services.sei_process import SEI_MAX_PER_PROJECT


def test_parses_semicolon_utf8():
    raw = "titulo;descricao\nProjeto A;Descrição A\nProjeto B;Descrição B".encode(
        "utf-8"
    )
    rows = parse_import_rows(raw)
    assert rows == [
        ParsedImportRow("Projeto A", "Descrição A"),
        ParsedImportRow("Projeto B", "Descrição B"),
    ]


def test_parses_comma_delimiter():
    raw = b"titulo,descricao\nA,desc A\nB,desc B"
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("A", "desc A"), ParsedImportRow("B", "desc B")]


def test_delimitador_ignora_linha_em_branco_antes_do_cabecalho():
    raw = b"\ntitulo,descricao\nProjeto A,desc"
    assert parse_import_rows(raw) == [ParsedImportRow("Projeto A", "desc")]


def test_delimitador_ignora_linhas_em_branco_com_mapeamento():
    raw = "\n\nTítulo,Dono\nProjeto A,Maria".encode("utf-8")
    assert parse_import_rows(raw, mapeamento={0: "titulo"}) == [
        ParsedImportRow(titulo="Projeto A")
    ]


def test_parses_utf8_with_bom():
    raw = "﻿titulo;descricao\nProjeto;Olá".encode("utf-8")
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("Projeto", "Olá")]


def test_parses_latin1_fallback():
    raw = "titulo;descricao\nProjeto;Inventário".encode("latin-1")
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("Projeto", "Inventário")]


def test_header_is_case_and_space_insensitive():
    raw = b" Titulo ; Descricao \nA;d"
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("A", "d")]


def test_skips_rows_without_title():
    raw = b"titulo;descricao\n;sem titulo\n   ;outra\nValido;ok"
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("Valido", "ok")]


def test_blank_description_is_kept_as_empty_string():
    raw = b"titulo;descricao\nSo titulo;"
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("So titulo", "")]


def test_missing_required_column_raises_with_context():
    raw = b"nome;descricao\nA;d"
    with pytest.raises(ValueError) as exc:
        parse_import_rows(raw)
    assert "titulo" in str(exc.value)


def test_empty_csv_raises():
    with pytest.raises(ValueError) as exc:
        parse_import_rows(b"   ")
    assert "vazio" in str(exc.value).lower()


def test_extra_columns_are_ignored():
    raw = b"titulo;descricao;status\nA;d;Vigente"
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("A", "d")]


def test_row_with_more_fields_than_header_does_not_raise():
    # Linha malformada: mais separadores que o cabeçalho. csv.DictReader coloca o
    # excedente sob a chave None (uma list); não deve estourar AttributeError.
    raw = b"titulo;descricao\nA;foo;bar"
    rows = parse_import_rows(raw)
    assert rows == [ParsedImportRow("A", "foo")]


def test_parse_com_mapeamento_fora_de_ordem():
    raw = "Dono;Descrição;Título do Projeto\nMaria;Desc A;Projeto A".encode("utf-8")
    rows = parse_import_rows(raw, mapeamento={2: "titulo", 1: "descricao"})
    assert rows == [ParsedImportRow(titulo="Projeto A", descricao="Desc A")]


def test_parse_sem_mapeamento_continua_legado():
    raw = b"titulo;descricao;status\nA;d;Finalizado"
    assert parse_import_rows(raw) == [ParsedImportRow("A", "d")]
    assert parse_import_rows(raw, mapeamento=None) == parse_import_rows(raw)


def test_parse_com_mapeamento_todos_os_campos():
    raw = (
        "Título,Situação,Entrega,Especial,Obs,Processos\n"
        'Projeto X,FINALIZADO,sistema,abep,Nota livre,"SEI-1; SEI-2"'
    ).encode("utf-8")
    mapeamento = {
        0: "titulo",
        1: "status",
        2: "delivery_type",
        3: "special_project",
        4: "observacao",
        5: "sei",
    }
    (row,) = parse_import_rows(raw, mapeamento=mapeamento)
    assert row.titulo == "Projeto X"
    assert row.status == "FINALIZADO"
    assert row.delivery_type == "sistema"
    assert row.special_project == "abep"
    assert row.observacao == "Nota livre"
    assert row.sei_numeros == ["SEI-1", "SEI-2"]


def test_mapeamento_preserva_linha_sem_titulo():
    raw = b"t;d\n;sem titulo\nOk;desc"
    rows = parse_import_rows(raw, mapeamento={0: "titulo", 1: "descricao"})
    assert [row.titulo for row in rows] == ["", "Ok"]


def test_sei_multivalor_e_status_acentuado():
    raw = 'Nome;Status;SEI\nP1;FINALIZADO;"SEI-1, SEI-2"'.encode("utf-8")
    (row,) = parse_import_rows(raw, mapeamento={0: "titulo", 1: "status", 2: "sei"})
    assert row.sei_numeros == ["SEI-1", "SEI-2"]
    attrs = _resolve_row_attributes(row, "VPD", "Vigente", None, None)
    assert attrs.status == "Finalizado"
    assert attrs.adjusted is False


def test_status_desconhecido_cai_no_default_e_conta_adjusted():
    row = ParsedImportRow(titulo="P", status="Concluído")
    attrs = _resolve_row_attributes(row, "VPD", "Vigente", None, None)
    assert attrs.status == "Vigente"
    assert attrs.adjusted is True


def test_delivery_e_special_normalizam_por_linha():
    row = ParsedImportRow(
        titulo="P", delivery_type="SISTEMA", special_project="fórum de simplificação"
    )
    attrs = _resolve_row_attributes(row, "VPD", "Vigente", None, None)
    assert attrs.delivery_type == "Sistema"
    assert attrs.special_project == "Fórum de simplificação"
    assert attrs.adjusted is False


def test_inventario_em_orgao_inelegivel_cai_no_default():
    row = ParsedImportRow(titulo="P", special_project="Inventário")
    attrs = _resolve_row_attributes(row, "SEFAZ", "Vigente", None, None)
    assert attrs.special_project is None
    assert attrs.adjusted is True


def test_inventario_em_orgao_elegivel_passa():
    row = ParsedImportRow(titulo="P", special_project="inventario")
    attrs = _resolve_row_attributes(row, "vpd", "Vigente", None, None)
    assert attrs.special_project == "Inventário"
    assert attrs.adjusted is False


def test_defaults_do_form_sem_valor_na_linha_nao_contam_adjusted():
    row = ParsedImportRow(titulo="P")
    attrs = _resolve_row_attributes(row, "VPD", "Suspenso", "TCE", "Painel")
    assert (attrs.status, attrs.special_project, attrs.delivery_type) == (
        "Suspenso",
        "TCE",
        "Painel",
    )
    assert attrs.adjusted is False


def test_filter_sei_descarta_item_acima_do_limite():
    kept, dropped = _filter_sei_numbers(["SEI-1", "9" * 60])
    assert kept == ["SEI-1"]
    assert dropped == 1


def test_filter_sei_trunca_no_teto_por_projeto():
    valores = [f"380001/{indice:06d}/2026" for indice in range(SEI_MAX_PER_PROJECT + 5)]
    kept, dropped = _filter_sei_numbers(valores)
    assert kept == valores[:SEI_MAX_PER_PROJECT]
    assert dropped == 5


def test_read_tabular_bytes_formato_desconhecido():
    with pytest.raises(ValueError) as exc:
        read_tabular_bytes(b"a;b", formato="xlsx")
    assert "xlsx" in str(exc.value)


def test_campo_gigante_vira_valueerror_e_nao_csv_error():
    raw = b"titulo;descricao\n" + b"a" * 200_000 + b";x\n"
    with pytest.raises(ValueError) as exc:
        parse_import_rows(raw)
    assert "CSV malformado" in str(exc.value)
    assert str(csv.field_size_limit()) in str(exc.value)


def test_linha_em_branco_inicial_do_excel_nao_vira_cabecalho():
    raw = ",,\nTítulo,Descrição\nPortal,Unifica\n".encode("utf-8")
    cabecalhos, linhas = read_tabular_bytes(raw)
    assert cabecalhos == ["Título", "Descrição"]
    assert linhas == [["Portal", "Unifica"]]


def test_linha_so_de_espacos_antes_do_cabecalho_e_descartada():
    raw = "   \nTítulo,Descrição\nPortal,Unifica\n".encode("utf-8")
    cabecalhos, linhas = read_tabular_bytes(raw)
    assert cabecalhos == ["Título", "Descrição"]
    assert linhas == [["Portal", "Unifica"]]


def test_linha_em_branco_no_meio_e_preservada_como_ignorada():
    raw = ",,\nTítulo,Descrição\nPortal,Unifica\n,,\n".encode("utf-8")
    _, linhas = read_tabular_bytes(raw)
    assert linhas == [["Portal", "Unifica"], ["", "", ""]]


def test_special_project_com_espaco_duplo_casa_no_catalogo():
    row = ParsedImportRow(titulo="P", special_project="Fórum  de simplificação")
    attrs = _resolve_row_attributes(row, "VPD", "Vigente", None, None)
    assert attrs.special_project == "Fórum de simplificação"
    assert attrs.adjusted is False
