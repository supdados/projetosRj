"""Testes unitários para services/import_values.py.

Módulo puro: cobre o parser de data tolerante e a normalização de prioridade
usados pelo import de projetos via CSV.
"""

from datetime import date

import pytest

from services.import_values import (
    EtapaSituacao,
    parse_flexible_date,
    parse_situacao,
    resolve_import_date,
    resolve_import_priority,
    resolve_responsaveis_entries,
)


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("31/12/2026", date(2026, 12, 31)),
        ("01/02/2026", date(2026, 2, 1)),
        ("2026-02-01", date(2026, 2, 1)),
        ("  2026-02-01  ", date(2026, 2, 1)),
        ("", None),
        ("   ", None),
        (None, None),
        ("ontem", None),
        ("31/31/2026", None),
        ("2026-13-01", None),
        ("01-02-2026", None),
        ("2026/02/01", None),
    ],
)
def test_parse_flexible_date(raw: str | None, esperado: date | None) -> None:
    assert parse_flexible_date(raw) == esperado


def test_parse_flexible_date_nunca_lanca_com_lixo() -> None:
    assert parse_flexible_date("😀;;;") is None


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("31/12/2026", (date(2026, 12, 31), True)),
        ("", (None, True)),
        (None, (None, True)),
        ("qualquer coisa", (None, False)),
    ],
)
def test_resolve_import_date(
    raw: str | None, esperado: tuple[date | None, bool]
) -> None:
    assert resolve_import_date(raw) == esperado


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("baixa", ("baixa", True)),
        ("MÉDIA", ("media", True)),
        ("  Média  ", ("media", True)),
        ("Urgente", ("urgente", True)),
        ("", (None, True)),
        (None, (None, True)),
        ("altíssima", (None, False)),
        ("P1", (None, False)),
    ],
)
def test_resolve_import_priority(
    raw: str | None, esperado: tuple[str | None, bool]
) -> None:
    assert resolve_import_priority(raw) == esperado


@pytest.mark.parametrize(
    "raw",
    ["concluida", "Concluído", "CONCLUÍDA", "sim", "S", "x", "1", "done", "TRUE"],
)
def test_parse_situacao_concluida(raw: str) -> None:
    assert parse_situacao(raw) == (EtapaSituacao(iniciada=True, done=True), True)


@pytest.mark.parametrize(
    "raw", ["em andamento", "EM  ANDAMENTO", "Andamento", "iniciada"]
)
def test_parse_situacao_em_andamento(raw: str) -> None:
    assert parse_situacao(raw) == (EtapaSituacao(iniciada=True, done=False), True)


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_parse_situacao_vazia_nao_iniciada_sem_ajuste(raw: str | None) -> None:
    assert parse_situacao(raw) == (EtapaSituacao(iniciada=False, done=False), True)


@pytest.mark.parametrize("raw", ["pausada", "0", "nope"])
def test_parse_situacao_desconhecida_conta_ajuste(raw: str) -> None:
    assert parse_situacao(raw) == (EtapaSituacao(iniciada=False, done=False), False)


_AREAS_IDS = {"vpd": 7, "coodados": 12}


def test_resolve_responsaveis_sigla_conhecida_casefold() -> None:
    entries, ok = resolve_responsaveis_entries(
        "VPD, coodados", _AREAS_IDS, "Outras áreas"
    )
    assert entries == [
        {"area_id": 7, "label": "VPD"},
        {"area_id": 12, "label": "coodados"},
    ]
    assert ok is True


def test_resolve_responsaveis_desconhecida_vira_outras_com_ajuste() -> None:
    entries, ok = resolve_responsaveis_entries("XPTO", _AREAS_IDS, "Outras áreas")
    assert entries == [{"area_id": None, "label": "Outras áreas"}]
    assert ok is False


def test_resolve_responsaveis_dedupe_por_area_e_por_outras() -> None:
    entries, ok = resolve_responsaveis_entries(
        "vpd, VPD, XPTO, ZZZ", _AREAS_IDS, "Outras áreas"
    )
    assert entries == [
        {"area_id": 7, "label": "vpd"},
        {"area_id": None, "label": "Outras áreas"},
    ]
    assert ok is False


@pytest.mark.parametrize("raw", ["", "   ", None, ", ,"])
def test_resolve_responsaveis_vazio(raw: str | None) -> None:
    assert resolve_responsaveis_entries(raw, _AREAS_IDS, "Outras áreas") == ([], True)
