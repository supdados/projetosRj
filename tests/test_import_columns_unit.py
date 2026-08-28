"""Testes unitários para services/import_columns.py.

O módulo é puro (sem Flask/DB): os casos cobrem normalização de cabeçalho,
sugestão de campo por nome e validação do form ``mapeamento``.
"""

import pytest

from services.import_columns import (
    IMPORT_FIELDS_COM_ETAPAS,
    IMPORT_FIELDS_ETAPA,
    IMPORT_FIELDS_PAYLOAD,
    IMPORT_FIELDS_SIMPLE,
    REQUIRED_IMPORT_FIELDS,
    REQUIRED_IMPORT_FIELDS_COM_ETAPAS,
    ColumnSuggestion,
    build_fields_payload,
    import_mode_fields,
    normalize_header,
    parse_mapping_form_value,
    score_field,
    suggest_column_mapping,
)

# Cabeçalhos exatos do export de projetos — round-trip export → import.
_HEADERS_DO_EXPORT = [
    "Título",
    "Descrição",
    "Status",
    "Prioridade",
    "Tipo de entrega",
    "Projeto especial",
    "Área responsável",
    "Órgão",
    "Observação",
    "Processos SEI",
    "Data de início",
    "Data de fim",
]


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
        parse_mapping_form_value('{"0":"titulo","1":"dono"}')
    assert str(exc.value) == (
        "Campo inválido no mapeamento: 'dono'. Use um de titulo, descricao, "
        "status, prioridade, delivery_type, special_project, area, orgao, "
        "observacao, sei, data_inicio, data_fim, ref_projeto, etapa, "
        "etapa_data_inicio, etapa_data_fim, etapa_responsavel, etapa_situacao, "
        "etapa_comentarios."
    )


def test_parse_mapping_aceita_campos_novos() -> None:
    assert parse_mapping_form_value(
        '{"0":"titulo","1":"prioridade","2":"area","3":"orgao","4":"data_inicio"}'
    ) == {0: "titulo", 1: "prioridade", 2: "area", 3: "orgao", 4: "data_inicio"}


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


def test_headers_do_export_casam_um_a_um_no_import() -> None:
    sugestoes = suggest_column_mapping(_HEADERS_DO_EXPORT)
    assert [s.campo for s in sugestoes] == list(IMPORT_FIELDS_SIMPLE)
    assert {s.confianca for s in sugestoes} == {"exato"}


def test_area_e_orgao_sao_campos_distintos() -> None:
    sugestoes = suggest_column_mapping(["Órgão", "Área responsável"])
    assert [s.campo for s in sugestoes] == ["orgao", "area"]


def test_datas_de_inicio_e_fim_nao_se_confundem() -> None:
    sugestoes = suggest_column_mapping(["Data de início", "Data de fim"])
    assert [s.campo for s in sugestoes] == ["data_inicio", "data_fim"]
    assert score_field("data fim", "data_inicio") is None


@pytest.mark.parametrize(
    ("cabecalho", "campo"),
    [
        ("PRIORIDADE", "prioridade"),
        ("Urgência", "prioridade"),
        ("Área", "area"),
        ("Sigla da área", "area"),
        ("Orgão", "orgao"),
        ("Órgão responsável", "orgao"),
        ("Início", "data_inicio"),
        ("Data inicial", "data_inicio"),
        ("Término", "data_fim"),
        ("Prazo", "data_fim"),
    ],
)
def test_sinonimos_dos_campos_novos(cabecalho: str, campo: str) -> None:
    assert suggest_column_mapping([cabecalho])[0].campo == campo


def test_suggest_restrito_a_um_subconjunto_de_campos() -> None:
    sugestoes = suggest_column_mapping(["Título", "Prioridade"], ("titulo",))
    assert [s.campo for s in sugestoes] == ["titulo", None]


def test_build_fields_payload_marca_obrigatorios() -> None:
    payload = build_fields_payload(("titulo", "prioridade"), frozenset({"titulo"}))
    assert payload == [
        {"campo": "titulo", "rotulo": "Título", "obrigatorio": True},
        {"campo": "prioridade", "rotulo": "Prioridade", "obrigatorio": False},
    ]


def test_payload_padrao_cobre_os_campos_do_modo_simples() -> None:
    assert [campo["campo"] for campo in IMPORT_FIELDS_PAYLOAD] == list(
        IMPORT_FIELDS_SIMPLE
    )
    assert REQUIRED_IMPORT_FIELDS == frozenset({"titulo"})


# Cabeçalhos exatos do export com etapas — round-trip export → import.
_HEADERS_ETAPA_DO_EXPORT = [
    "Ref Projeto",
    "Etapa",
    "Etapa Data de início",
    "Etapa Data de fim",
    "Etapa Responsável",
    "Etapa Situação",
    "Etapa Comentários",
]


def test_headers_de_etapa_do_export_casam_um_a_um() -> None:
    sugestoes = suggest_column_mapping(_HEADERS_ETAPA_DO_EXPORT)
    assert [s.campo for s in sugestoes] == list(IMPORT_FIELDS_ETAPA)
    assert {s.confianca for s in sugestoes} == {"exato"}


def test_etapa_nao_rouba_o_match_das_colunas_compostas() -> None:
    sugestoes = suggest_column_mapping(["Etapa Data de início", "Etapa"])
    assert [s.campo for s in sugestoes] == ["etapa_data_inicio", "etapa"]


def test_data_de_inicio_do_projeto_e_da_etapa_sao_distintas() -> None:
    sugestoes = suggest_column_mapping(["Data de início", "Etapa Data de início"])
    assert [s.campo for s in sugestoes] == ["data_inicio", "etapa_data_inicio"]


def test_import_mode_fields_por_modo() -> None:
    assert import_mode_fields("simples") == (
        IMPORT_FIELDS_SIMPLE,
        REQUIRED_IMPORT_FIELDS,
    )
    assert import_mode_fields("com_etapas") == (
        IMPORT_FIELDS_COM_ETAPAS,
        REQUIRED_IMPORT_FIELDS_COM_ETAPAS,
    )
    with pytest.raises(ValueError) as exc:
        import_mode_fields("turbo")
    assert str(exc.value).startswith("Modo inválido: 'turbo'")


def test_campos_com_etapas_nao_tem_datas_de_projeto() -> None:
    assert "data_inicio" not in IMPORT_FIELDS_COM_ETAPAS
    assert "data_fim" not in IMPORT_FIELDS_COM_ETAPAS
    assert REQUIRED_IMPORT_FIELDS_COM_ETAPAS == frozenset(
        {"titulo", "ref_projeto", "etapa"}
    )


def test_parse_mapping_modo_simples_recusa_campo_de_etapa() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('{"0":"titulo","1":"ref_projeto"}')
    assert str(exc.value).startswith(
        "Campo 'ref_projeto' não está disponível no modo 'simples'."
    )


def test_parse_mapping_com_etapas_exige_ref_e_etapa() -> None:
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('{"0":"titulo","1":"etapa"}', "com_etapas")
    assert "Ref do projeto" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value('{"0":"titulo","1":"ref_projeto"}', "com_etapas")
    assert str(exc.value) == "Mapeie a coluna da etapa no modo com etapas."


def test_parse_mapping_com_etapas_recusa_data_de_projeto() -> None:
    raw = '{"0":"titulo","1":"ref_projeto","2":"etapa","3":"data_inicio"}'
    with pytest.raises(ValueError) as exc:
        parse_mapping_form_value(raw, "com_etapas")
    assert str(exc.value).startswith(
        "Campo 'data_inicio' não está disponível no modo 'com_etapas'."
    )


def test_parse_mapping_com_etapas_completo() -> None:
    raw = '{"0":"ref_projeto","1":"titulo","2":"etapa","3":"etapa_situacao"}'
    assert parse_mapping_form_value(raw, "com_etapas") == {
        0: "ref_projeto",
        1: "titulo",
        2: "etapa",
        3: "etapa_situacao",
    }
