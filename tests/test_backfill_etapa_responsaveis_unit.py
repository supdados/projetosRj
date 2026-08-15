"""Testes do backfill one-shot espelho Etapa.responsavel -> N:N EtapaResponsavel.

Sprint 3.1: a N:N vira a face canônica e o espelho passa a ser derivado.
Cobre: conversão espelho->N:N (sigla viva casada + rótulo sem área preservado),
idempotência (segunda rodada não encontra pendentes), espelho vazio/branco fora
do alvo e dry-run sem escrita.
"""

from models import Etapa, EtapaResponsavel, OrgaoUnidade, Project, db
from scripts.migrations.backfill_etapa_responsaveis import (
    _converter_etapas,
    _etapas_pendentes,
)


def _create_area(sigla: str) -> OrgaoUnidade:
    area = OrgaoUnidade(sigla=sigla, nome=f"Área {sigla}", tipo="Secretaria", ordem=0)
    db.session.add(area)
    db.session.flush()
    return area


def _create_etapa(responsavel: str | None) -> Etapa:
    project = Project(titulo="Projeto Backfill")
    db.session.add(project)
    db.session.flush()
    etapa = Etapa(
        descricao="Etapa Y", project_id=project.id, ordem=0, responsavel=responsavel
    )
    db.session.add(etapa)
    db.session.flush()
    return etapa


def test_backfill_converte_espelho_em_linhas_nn(app):
    with app.app_context():
        area = _create_area("SUBEXE")
        etapa = _create_etapa("SUBEXE, Time externo")

        stats = _converter_etapas(_etapas_pendentes(), aplicar=True)
        db.session.commit()

        assert stats == {
            "convertidas": 1,
            "linhas": 2,
            "com_area": 1,
            "sem_area": 1,
            "multi_sem_area": [],
        }
        rows = [
            (r.area_id, r.label) for r in db.session.get(Etapa, etapa.id).responsaveis
        ]
        assert rows == [(area.id, "SUBEXE"), (None, "Time externo")]
        assert db.session.get(Etapa, etapa.id).responsavel == "SUBEXE, Time externo"


def test_backfill_preserva_multiplos_rotulos_sem_area(app):
    with app.app_context():
        etapa = _create_etapa("Time A, Time B")

        stats = _converter_etapas(_etapas_pendentes(), aplicar=True)
        db.session.commit()

        assert stats["multi_sem_area"] == [(etapa.id, ["Time A", "Time B"])]
        rows = [
            (r.area_id, r.label) for r in db.session.get(Etapa, etapa.id).responsaveis
        ]
        assert rows == [(None, "Time A"), (None, "Time B")]


def test_backfill_barra_so_separa_quando_todas_as_partes_sao_siglas(app):
    with app.app_context():
        _create_area("SUPIM")
        _create_area("SUBDGD")
        etapa_lista = _create_etapa("SUPIM/SUBDGD")
        etapa_nome = _create_etapa("Contrato Nº 004/2024")

        _converter_etapas(_etapas_pendentes(), aplicar=True)
        db.session.commit()

        labels_lista = [
            r.label for r in db.session.get(Etapa, etapa_lista.id).responsaveis
        ]
        labels_nome = [
            r.label for r in db.session.get(Etapa, etapa_nome.id).responsaveis
        ]
        assert labels_lista == ["SUPIM", "SUBDGD"]
        assert labels_nome == ["Contrato Nº 004/2024"]
        assert db.session.get(Etapa, etapa_nome.id).responsavel == "Contrato Nº 004/2024"


def test_backfill_e_idempotente(app):
    with app.app_context():
        etapa = _create_etapa("SUPIM")
        _converter_etapas(_etapas_pendentes(), aplicar=True)
        db.session.commit()

        assert _etapas_pendentes() == []
        stats = _converter_etapas(_etapas_pendentes(), aplicar=True)
        assert stats["convertidas"] == 0
        assert len(db.session.get(Etapa, etapa.id).responsaveis) == 1


def test_backfill_ignora_espelho_vazio_ou_em_branco(app):
    with app.app_context():
        _create_etapa(None)
        _create_etapa("   ")
        assert _etapas_pendentes() == []


def test_backfill_ignora_etapa_que_ja_tem_nn(app):
    with app.app_context():
        etapa = _create_etapa("SUPGEST")
        etapa.responsaveis.append(EtapaResponsavel(area_id=None, label="Outras"))
        db.session.flush()
        assert _etapas_pendentes() == []


def test_backfill_dry_run_nao_escreve(app):
    with app.app_context():
        etapa = _create_etapa("SUPIM")

        stats = _converter_etapas(_etapas_pendentes(), aplicar=False)
        db.session.commit()

        assert stats["convertidas"] == 1
        assert db.session.get(Etapa, etapa.id).responsaveis == []
