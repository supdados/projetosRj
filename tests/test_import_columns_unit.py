"""Testes unitários para services/import_columns.py.

O módulo é puro (sem Flask/DB): os casos cobrem normalização de cabeçalho,
sugestão de campo por nome e validação do form ``mapeamento``.
"""

import pytest

from services.import_columns import (
    IMPORT_FIELDS_PAYLOAD,
    ColumnSuggestion,
    normalize_header,
    parse_mapping_form_value,
    score_field,
    suggest_column_mapping,
)


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("Título", "titulo"),
        ("DESCRIÇÃO", "descricao"),
        ("titulo_do_projeto", "titulo projeto"),
        ("Nome do Projeto", "nome projeto"),
        ("  Processos   SEI  ", "processos sei"),
        ("Observação (interna)", "observacao interna"),
        ("Tipo de Entrega", "tipo entrega"),
        ("", ""),
    ],
)
def test_normalize_header(raw: str, esperado: str) -> None:
    assert normalize_header(raw) == esperado


def test_suggest_exato_sinonimo_fuzzy() -> None:
    assert suggest_column_mapping(["Título"]) == [
        ColumnSuggestion(0, "Título", "titulo", "exato")
    ]
    assert suggest_column_mapping(["nome"])[0].confianca == "sinonimo"
    aproximado = suggest_column_mapping(["titullo"])[0]
    assert (aproximado.campo, aproximado.confianca) == ("titulo", "aproximado")


def test_suggest_cabecalhos_reais_fora_de_ordem() -> None:
    headers = ["Descrição", "Título do Projeto", "Situação", "Processo SEI RJ"]
    campos = [s.campo for s in suggest_column_mapping(headers)]
    assert campos == ["descricao", "titulo", "status", "sei"]


def test_disputa_de_campo_menor_indice_vence() -> None:
    sugestoes = suggest_column_mapping(["nome", "Nome do Projeto"])
    assert sugestoes[0].campo == "titulo"
    assert sugestoes[1].campo is None
    assert sugestoes[1].confianca is None


def test_maior_score_vence_menor_indice() -> None:
    sugestoes = suggest_column_mapping(["nome", "Título"])
    assert [s.campo for s in sugestoes] == [None, "titulo"]


def test_cabecalho_ambiguo_nao_mapeia() -> None:
    sugestoes = suggest_column_mapping(["tipo", "Dono"])
    assert [s.campo for s in sugestoes] == [None, None]
    assert score_field("tipo", "delivery_type") is None


def test_cabecalho_vazio_e_duplicado_nao_explode() -> None:
    sugestoes = suggest_column_mapping(["", "  ", "Título", "Título"])
    assert [s.campo for s in sugestoes] == [None, None, "titulo", None]
    assert suggest_column_mapping([]) == []


def test_campos_payload_marca_titulo_obrigatorio() -> None:
    obrigatorios = [c["campo"] for c in IMPORT_FIELDS_PAYLOAD if c["obrigatorio"]]
    assert obrigatorios == ["titulo"]
    assert IMPORT_FIELDS_PAYLOAD[0]["rotulo"] == "Título"


def test_parse_mapping_form_value() -> None:
    assert parse_mapping_form_value('{"0":"titulo","3":"descricao"}') == {
        0: "titulo",
        3: "descricao",
    }


def test_parse_mapping_json_invalido() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value("nao-e-json")
    assert str(exc.value) == (
        "Mapeamento inválido: 'nao-e-json' (esperado JSON de índice para campo)."
    )


def test_parse_mapping_lista_invalida() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('["titulo"]')
    assert "esperado JSON de índice para campo" in str(exc.value)


def test_parse_mapping_campo_fora_da_whitelist() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('{"0":"titulo","1":"prioridade"}')
    assert str(exc.value) == (
        "Campo inválido no mapeamento: 'prioridade'. Use um de titulo, descricao, "
        "status, delivery_type, special_project, observacao, sei."
    )


def test_parse_mapping_campo_duplicado() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('{"0":"titulo","1":"titulo"}')
    assert str(exc.value) == "Campo 'titulo' mapeado em mais de uma coluna."


def test_parse_mapping_sem_titulo() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('{"0":"descricao"}')
    assert str(exc.value) == "Mapeie a coluna do título antes de importar."


def test_parse_mapping_indice_nao_numerico() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('{"coluna":"titulo"}')
    assert "esperado JSON de índice para campo" in str(exc.value)
