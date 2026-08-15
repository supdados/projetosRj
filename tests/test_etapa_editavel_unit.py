"""Testes unitários do invariante centralizado "etapa editável" (item 1.1)."""

import pytest

from services.etapa_responsaveis import MOTIVO_RESPONSAVEIS_ETAPA_CONCLUIDA
from services.etapas_mutation import (
    MOTIVO_COMENTARIO_ETAPA_CONCLUIDA,
    MOTIVO_ETAPA_CONCLUIDA,
    MOTIVO_PROJETO_FINALIZADO,
    EtapaNaoEditavelError,
    assert_etapa_editavel,
    assert_projeto_permite_mutacao_de_etapas,
)


class FakeProjetoStatus:
    def __init__(self, status: str) -> None:
        self.status = status


class FakeEtapaEditavel:
    def __init__(self, *, status: str = "Vigente", done: bool = False) -> None:
        self.project = FakeProjetoStatus(status)
        self.done = done


def test_etapa_aberta_de_projeto_vigente_passa() -> None:
    assert_etapa_editavel(FakeEtapaEditavel())


def test_projeto_finalizado_levanta_com_codigo_e_motivo() -> None:
    with pytest.raises(EtapaNaoEditavelError) as exc_info:
        assert_etapa_editavel(FakeEtapaEditavel(status="Finalizado"))

    assert exc_info.value.codigo == "projeto_finalizado"
    assert exc_info.value.motivo == MOTIVO_PROJETO_FINALIZADO


def test_etapa_concluida_levanta_com_motivo_padrao() -> None:
    with pytest.raises(EtapaNaoEditavelError) as exc_info:
        assert_etapa_editavel(FakeEtapaEditavel(done=True))

    assert exc_info.value.codigo == "etapa_concluida"
    assert exc_info.value.motivo == MOTIVO_ETAPA_CONCLUIDA


def test_etapa_concluida_com_allow_done_passa() -> None:
    assert_etapa_editavel(FakeEtapaEditavel(done=True), allow_done=True)


def test_motivo_done_personalizado_e_propagado() -> None:
    with pytest.raises(EtapaNaoEditavelError) as exc_info:
        assert_etapa_editavel(
            FakeEtapaEditavel(done=True),
            motivo_done=MOTIVO_COMENTARIO_ETAPA_CONCLUIDA,
        )

    assert exc_info.value.motivo == MOTIVO_COMENTARIO_ETAPA_CONCLUIDA


def test_motivo_done_de_responsaveis_e_propagado() -> None:
    with pytest.raises(EtapaNaoEditavelError) as exc_info:
        assert_etapa_editavel(
            FakeEtapaEditavel(done=True),
            motivo_done=MOTIVO_RESPONSAVEIS_ETAPA_CONCLUIDA,
        )

    assert exc_info.value.motivo == MOTIVO_RESPONSAVEIS_ETAPA_CONCLUIDA


def test_finalizado_prevalece_sobre_done_mesmo_com_allow_done() -> None:
    with pytest.raises(EtapaNaoEditavelError) as exc_info:
        assert_etapa_editavel(
            FakeEtapaEditavel(status="Finalizado", done=True), allow_done=True
        )

    assert exc_info.value.codigo == "projeto_finalizado"


def test_assert_projeto_vigente_passa() -> None:
    assert_projeto_permite_mutacao_de_etapas(FakeProjetoStatus("Vigente"))


def test_assert_projeto_finalizado_levanta() -> None:
    with pytest.raises(EtapaNaoEditavelError) as exc_info:
        assert_projeto_permite_mutacao_de_etapas(FakeProjetoStatus("Finalizado"))

    assert exc_info.value.codigo == "projeto_finalizado"


def test_excecao_e_valueerror_para_rotas_legadas() -> None:
    # Rotas legadas condenadas só tratam ValueError: a herança evita 500.
    assert issubclass(EtapaNaoEditavelError, ValueError)
