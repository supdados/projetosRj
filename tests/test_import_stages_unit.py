"""Testes unitários para routes/projects/import_stages.py.

``group_stage_rows`` é pura (recebe ``ParsedImportRow`` já parseados): os casos
cobrem contiguidade dos grupos, herança da 1ª linha, divergência, etapa default
e as validações de ref/título/etapa com o número da linha na mensagem.
"""

import pytest

from routes.projects.import_csv import ParsedImportRow
from routes.projects.import_stages import (
    ParsedImportProject,
    ParsedStage,
    _is_blank_import_row,
    group_stage_rows,
)


def _linha(**kwargs) -> ParsedImportRow:
    return ParsedImportRow(titulo=kwargs.pop("titulo", ""), **kwargs)


def test_agrupa_refs_contiguas_com_ordem_das_etapas() -> None:
    grupos = group_stage_rows(
        [
            _linha(titulo="P1", ref_projeto="p1", etapa="Levantamento"),
            _linha(ref_projeto="p1", etapa="Execução"),
            _linha(ref_projeto="p1", etapa="Entrega"),
            _linha(titulo="P2", ref_projeto="p2", etapa="Planejamento"),
        ]
    )
    assert [grupo.projeto.titulo for grupo in grupos] == ["P1", "P2"]
    assert [etapa.descricao for etapa in grupos[0].etapas] == [
        "Levantamento",
        "Execução",
        "Entrega",
    ]
    assert [etapa.primeira for etapa in grupos[0].etapas] == [True, False, False]


def test_ref_e_normalizada_com_strip_e_casefold() -> None:
    grupos = group_stage_rows(
        [
            _linha(titulo="P1", ref_projeto=" A ", etapa="E1"),
            _linha(ref_projeto="a", etapa="E2"),
        ]
    )
    assert len(grupos) == 1
    assert len(grupos[0].etapas) == 2


def test_ref_reaparecendo_apos_outra_ref_levanta_com_a_linha() -> None:
    with pytest.raises(ValueError) as exc:
        group_stage_rows(
            [
                _linha(titulo="P1", ref_projeto="p1", etapa="E1"),
                _linha(titulo="P2", ref_projeto="p2", etapa="E1"),
                _linha(ref_projeto="p1", etapa="E2"),
            ]
        )
    assert str(exc.value) == (
        "Linha 4: linhas do projeto 'p1' não são contíguas — "
        "a planilha foi reordenada?"
    )


def test_ref_vazia_levanta_com_a_linha() -> None:
    with pytest.raises(ValueError) as exc:
        group_stage_rows(
            [
                _linha(titulo="P1", ref_projeto="p1", etapa="E1"),
                _linha(titulo="P2", etapa="E1"),
            ]
        )
    assert str(exc.value).startswith("Linha 3: ref_projeto vazio")


def test_titulo_ausente_na_primeira_linha_levanta_com_a_ref() -> None:
    with pytest.raises(ValueError) as exc:
        group_stage_rows([_linha(ref_projeto="p9", etapa="E1")])
    assert str(exc.value) == (
        "Linha 2: a primeira linha do projeto 'p9' precisa do título."
    )


def test_linha_subsequente_herda_sem_divergencia() -> None:
    grupos = group_stage_rows(
        [
            _linha(titulo="P1", ref_projeto="p1", etapa="E1", orgao="Secretaria X"),
            _linha(ref_projeto="p1", etapa="E2", orgao="Secretaria X"),
            _linha(ref_projeto="p1", etapa="E3"),
        ]
    )
    assert [etapa.divergente for etapa in grupos[0].etapas] == [False, False, False]


def test_campo_preenchido_divergente_marca_a_linha() -> None:
    grupos = group_stage_rows(
        [
            _linha(titulo="P1", ref_projeto="p1", etapa="E1"),
            _linha(titulo="Outro título", ref_projeto="p1", etapa="E2"),
        ]
    )
    grupo = grupos[0]
    # A 1ª linha vence: os campos de projeto continuam os dela.
    assert grupo.projeto.titulo == "P1"
    assert grupo.etapas[1].divergente is True


def test_sei_divergente_marca_a_linha() -> None:
    grupos = group_stage_rows(
        [
            _linha(titulo="P1", ref_projeto="p1", etapa="E1", sei_numeros=["SEI-1"]),
            _linha(ref_projeto="p1", etapa="E2", sei_numeros=["SEI-2"]),
        ]
    )
    assert grupos[0].etapas[1].divergente is True


def test_grupo_de_uma_linha_sem_etapa_ganha_a_default() -> None:
    grupos = group_stage_rows(
        [_linha(titulo="P1", ref_projeto="p1", etapa_data_inicio="01/02/2026")]
    )
    (etapa,) = grupos[0].etapas
    assert etapa == ParsedStage(
        descricao="Etapas a definir", data_inicio="01/02/2026", primeira=True
    )


def test_etapa_vazia_em_linha_subsequente_levanta_com_a_linha() -> None:
    with pytest.raises(ValueError) as exc:
        group_stage_rows(
            [
                _linha(titulo="P1", ref_projeto="p1", etapa="E1"),
                _linha(ref_projeto="p1", etapa="   "),
            ]
        )
    assert str(exc.value).startswith("Linha 3: etapa vazia no projeto 'p1'")


def test_linha_totalmente_vazia_e_pulada_sem_quebrar_o_grupo() -> None:
    grupos = group_stage_rows(
        [
            _linha(titulo="P1", ref_projeto="p1", etapa="E1"),
            _linha(),
            _linha(ref_projeto="p1", etapa="E2"),
        ]
    )
    assert len(grupos) == 1
    assert [etapa.descricao for etapa in grupos[0].etapas] == ["E1", "E2"]


def test_is_blank_import_row_olha_todas_as_celulas() -> None:
    assert _is_blank_import_row(_linha()) is True
    assert _is_blank_import_row(_linha(titulo="  ")) is True
    assert _is_blank_import_row(_linha(etapa_comentarios="obs")) is False
    assert _is_blank_import_row(_linha(sei_numeros=["SEI-1"])) is False


def test_etapa_carrega_os_campos_crus_da_linha() -> None:
    grupos = group_stage_rows(
        [
            _linha(
                titulo="P1",
                ref_projeto="p1",
                etapa="  Levantamento  ",
                etapa_data_inicio="01/02/2026",
                etapa_data_fim="2026-03-31",
                etapa_responsavel="vpd, XPTO",
                etapa_situacao="concluída",
                etapa_comentarios="Kickoff",
            )
        ]
    )
    (etapa,) = grupos[0].etapas
    assert etapa == ParsedStage(
        descricao="Levantamento",
        data_inicio="01/02/2026",
        data_fim="2026-03-31",
        responsavel="vpd, XPTO",
        situacao="concluída",
        comentarios="Kickoff",
        primeira=True,
    )


def test_grupo_guarda_a_ref_normalizada() -> None:
    grupos = group_stage_rows([_linha(titulo="P1", ref_projeto="Ref A", etapa="E1")])
    assert grupos == [
        ParsedImportProject(
            ref="ref a",
            projeto=_linha(titulo="P1", ref_projeto="Ref A", etapa="E1"),
            etapas=[ParsedStage(descricao="E1", primeira=True)],
        )
    ]
