"""Testes unitários para routes/projects/import_csv.py.

``parse_import_rows`` recebe bytes crus e não depende de Flask/DB, portanto
todos os casos aqui são puros — cobrem detecção de encoding, separador,
cabeçalho ausente e filtragem de linhas sem título.
"""

import pytest

from routes.projects.import_csv import ParsedImportRow, parse_import_rows


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
