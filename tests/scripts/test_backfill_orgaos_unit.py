"""Backfill de orgaos: resolucao de sigla legada e escrita a partir dos espelhos.

O modulo `scripts.catalog.organograma_siorg` e substituido por um fake nomeado
(`_OrganogramaFake`) para que os testes nao dependam do CSV do SIORG.
"""

from __future__ import annotations

import sys
import types

import pytest
from sqlalchemy import text

from models import db
from scripts.migrations.backfill_orgaos import (
    _ESPELHOS_LEGADOS,
    TABELA_PRE_COLAPSO,
    ColapsoJaAplicado,
    EspelhoLegadoInconsistente,
    criar_snapshots_legado,
    mapear_siglas,
    normalizar_sigla,
    run_backfill_orgaos,
    snapshot_user_orgao_pre_colapso,
)


class _OrganogramaFake:
    """Substituto de `scripts.catalog.organograma_siorg` com dados fixos."""

    def __init__(
        self,
        alias: dict[str, int],
        duplos: dict[str, tuple[int, int]],
        orgao_por_codigo: dict[int, int],
    ) -> None:
        self.ALIAS_SIGLA_LEGADA = alias
        self.VINCULOS_DUPLOS = duplos
        self._orgao_por_codigo = orgao_por_codigo

    def resolver_orgao_id_por_codigo(self) -> dict[int, int]:
        return self._orgao_por_codigo

    def instalar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        modulo = types.ModuleType("scripts.catalog.organograma_siorg")
        modulo.ALIAS_SIGLA_LEGADA = self.ALIAS_SIGLA_LEGADA
        modulo.VINCULOS_DUPLOS = self.VINCULOS_DUPLOS
        modulo.resolver_orgao_id_por_codigo = self.resolver_orgao_id_por_codigo
        monkeypatch.setitem(sys.modules, "scripts.catalog.organograma_siorg", modulo)


def test_normalizar_sigla_aplica_trim_upper_e_colapso() -> None:
    assert normalizar_sigla("  supim ") == "SUPIM"
    assert normalizar_sigla("RH -  PRODERJ") == "RH - PRODERJ"
    assert normalizar_sigla(None) == ""


def test_mapear_siglas_resolve_alias_e_expande_vinculo_duplo() -> None:
    mapa = mapear_siglas(
        {"SUPIM", "GAR/GFS"},
        alias_sigla={"SUPIM": 12, "GAR": 67, "GFS": 69},
        vinculos_duplos={"GAR/GFS": (67, 69)},
        orgao_por_codigo={12: 1, 67: 2, 69: 3},
    )
    assert mapa == {"SUPIM": (1,), "GAR/GFS": (2, 3)}


def test_mapear_siglas_ignora_sigla_com_codigo_nao_importado() -> None:
    mapa = mapear_siglas(
        {"SUPIM", "GAR/GFS", "DESCONHECIDA"},
        alias_sigla={"SUPIM": 12},
        vinculos_duplos={"GAR/GFS": (67, 69)},
        orgao_por_codigo={12: 1, 67: 2},
    )
    # GAR/GFS so resolveu metade do par: fica de fora inteira, sem vinculo torto.
    assert mapa == {"SUPIM": (1,)}


def test_espelhos_geram_ddl_e_copia_portaveis() -> None:
    espelho = next(e for e in _ESPELHOS_LEGADOS if e.destino == "legacy_project_area")
    assert espelho.ddl() == (
        "CREATE TABLE IF NOT EXISTS legacy_project_area "
        "(project_id INTEGER NOT NULL, area_responsavel VARCHAR(255) NOT NULL)"
    )
    assert espelho.copia() == (
        "INSERT INTO legacy_project_area (project_id, area_responsavel) "
        "SELECT id, area_responsavel FROM project WHERE area_responsavel IS NOT NULL"
    )


def _criar_orgao(sigla: str, codigo_externo: str) -> int:
    db.session.execute(
        text(
            "INSERT INTO orgao_unidade (nome, sigla, tipo, ordem, ativo, codigo_externo) "
            "VALUES (:nome, :sigla, 'Secretaria', 0, 1, :codigo)"
        ),
        {"nome": sigla, "sigla": sigla, "codigo": codigo_externo},
    )
    return int(
        db.session.execute(
            text("SELECT id FROM orgao_unidade WHERE sigla = :sigla"), {"sigla": sigla}
        ).scalar()
    )


def _criar_espelhos_legados(
    pares_projeto: list[tuple[int, str]], pares_usuario: list[tuple[int, str]]
) -> None:
    for espelho in _ESPELHOS_LEGADOS:
        db.session.execute(text(espelho.ddl()))
    db.session.execute(
        text(
            "INSERT INTO legacy_project_area (project_id, area_responsavel) "
            "VALUES (:project_id, :area)"
        ),
        [{"project_id": pid, "area": area} for pid, area in pares_projeto],
    )
    db.session.execute(
        text("INSERT INTO legacy_user_areas (user_id, area) VALUES (:user_id, :area)"),
        [{"user_id": uid, "area": area} for uid, area in pares_usuario],
    )


def _criar_projeto(titulo: str) -> int:
    db.session.execute(
        text("INSERT INTO project (titulo, status) VALUES (:titulo, 'Em andamento')"),
        {"titulo": titulo},
    )
    return int(
        db.session.execute(
            text("SELECT id FROM project WHERE titulo = :titulo"), {"titulo": titulo}
        ).scalar()
    )


def _criar_usuario(username: str) -> int:
    db.session.execute(
        text(
            "INSERT INTO user (username, password_hash, name, is_admin, is_super_admin, "
            "failed_login_attempts) VALUES (:u, 'x', :u, 0, 0, 0)"
        ),
        {"u": username},
    )
    return int(
        db.session.execute(
            text("SELECT id FROM user WHERE username = :u"), {"u": username}
        ).scalar()
    )


@pytest.fixture
def cenario_legado(app, monkeypatch):
    """Espelhos legados + 3 unidades SIORG, com o organograma fake instalado."""
    with app.app_context():
        supim = _criar_orgao("SUPIM", "12")
        gar = _criar_orgao("GAR", "67")
        gfs = _criar_orgao("GFS", "69")
        projeto_supim = _criar_projeto("Projeto SUPIM")
        projeto_duplo = _criar_projeto("Projeto GAR/GFS")
        projeto_orfao = _criar_projeto("Projeto sem area")
        usuario = _criar_usuario("fulano")
        _criar_espelhos_legados(
            pares_projeto=[
                (projeto_supim, " supim "),
                (projeto_duplo, "GAR/GFS"),
                (projeto_orfao, "INEXISTENTE"),
            ],
            # SUPIM repetida: o backfill precisa deduplicar antes do INSERT.
            pares_usuario=[
                (usuario, "SUPIM"),
                (usuario, "supim"),
                (usuario, "GAR/GFS"),
                (usuario, "INEXISTENTE"),
            ],
        )
        db.session.commit()
        _OrganogramaFake(
            alias={"SUPIM": 12, "GAR": 67, "GFS": 69},
            duplos={"GAR/GFS": (67, 69)},
            orgao_por_codigo={12: supim, 67: gar, 69: gfs},
        ).instalar(monkeypatch)
        yield {
            "supim": supim,
            "gar": gar,
            "gfs": gfs,
            "projeto_supim": projeto_supim,
            "projeto_duplo": projeto_duplo,
            "projeto_orfao": projeto_orfao,
            "usuario": usuario,
        }


def test_backfill_liga_projetos_e_deduplica_vinculos(app, cenario_legado) -> None:
    with app.app_context():
        report = run_backfill_orgaos(dry_run=False)

        assert report.fonte_projetos == "legacy_project_area"
        assert report.fonte_user_areas == "legacy_user_areas"
        assert report.projects_linked == 2
        assert report.projects_unmatched == ["INEXISTENTE"]
        assert report.user_areas_unmatched == ["INEXISTENTE"]

        orgaos = dict(
            db.session.execute(text("SELECT id, orgao_id FROM project")).all()
        )
        assert orgaos[cenario_legado["projeto_supim"]] == cenario_legado["supim"]
        # Sigla dupla em projeto: dono e a primeira unidade do par.
        assert orgaos[cenario_legado["projeto_duplo"]] == cenario_legado["gar"]
        assert orgaos[cenario_legado["projeto_orfao"]] is None

        vinculos = db.session.execute(
            text("SELECT orgao_id, papel FROM user_orgao ORDER BY orgao_id")
        ).all()
        assert sorted(orgao_id for orgao_id, _ in vinculos) == sorted(
            [cenario_legado["supim"], cenario_legado["gar"], cenario_legado["gfs"]]
        )
        assert {papel for _, papel in vinculos} == {"gestor"}


def test_segunda_execucao_nao_duplica(app, cenario_legado) -> None:
    with app.app_context():
        run_backfill_orgaos(dry_run=False)
        report = run_backfill_orgaos(dry_run=False)
        assert report.projects_linked == 0
        assert report.user_orgaos_linked == 0
        assert report.user_orgaos_existentes == 3


def test_dry_run_nao_grava(app, cenario_legado) -> None:
    with app.app_context():
        report = run_backfill_orgaos()
        assert report.projects_linked == 2
        assert db.session.execute(text("SELECT COUNT(*) FROM user_orgao")).scalar() == 0
        assert (
            db.session.execute(
                text("SELECT COUNT(*) FROM project WHERE orgao_id IS NOT NULL")
            ).scalar()
            == 0
        )


def test_criar_snapshots_ignora_origem_ja_dropada(app) -> None:
    """No head as tabelas legadas nao existem mais: nada e copiado, sem erro."""
    with app.app_context():
        assert criar_snapshots_legado() == {
            "legacy_user_areas": 0,
            "legacy_area_catalog": 0,
            "legacy_project_area": 0,
            "legacy_user_area_responsavel": 0,
        }


def _contar(tabela: str) -> int:
    return int(db.session.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar())


def test_backfill_aborta_quando_vinculo_foi_podado(app, cenario_legado) -> None:
    """A poda do colapso apaga linhas de user_orgao sem mexer na fonte legada."""
    with app.app_context():
        run_backfill_orgaos(dry_run=False)
        db.session.execute(
            text("DELETE FROM user_orgao WHERE orgao_id = :oid"),
            {"oid": cenario_legado["gfs"]},
        )
        db.session.commit()

        with pytest.raises(ColapsoJaAplicado, match="voltariam"):
            run_backfill_orgaos(dry_run=False)
        assert _contar("user_orgao") == 2


def test_backfill_aborta_com_a_marca_de_colapso(app, cenario_legado) -> None:
    with app.app_context():
        run_backfill_orgaos(dry_run=False)
        assert snapshot_user_orgao_pre_colapso() == 3
        db.session.commit()

        with pytest.raises(ColapsoJaAplicado, match=TABELA_PRE_COLAPSO):
            run_backfill_orgaos()


def test_snapshot_pre_colapso_e_idempotente(app, cenario_legado) -> None:
    with app.app_context():
        run_backfill_orgaos(dry_run=False)
        assert snapshot_user_orgao_pre_colapso() == 3
        assert snapshot_user_orgao_pre_colapso() == 0
        assert _contar(TABELA_PRE_COLAPSO) == 3


def _criar_user_areas(pares: list[tuple[int, str]]) -> None:
    db.session.execute(
        text(
            "CREATE TABLE user_areas "
            "(id INTEGER PRIMARY KEY, user_id INTEGER, area VARCHAR(100))"
        )
    )
    db.session.execute(
        text("INSERT INTO user_areas (user_id, area) VALUES (:user_id, :area)"),
        [{"user_id": uid, "area": area} for uid, area in pares],
    )


def test_espelho_parcial_de_ensaio_anterior_e_refeito(app) -> None:
    """Espelho com menos linhas que a origem seria backup incompleto no drop."""
    with app.app_context():
        _criar_user_areas([(1, "SUPIM"), (2, "GAR"), (3, "GFS")])
        espelho = next(e for e in _ESPELHOS_LEGADOS if e.destino == "legacy_user_areas")
        db.session.execute(text(espelho.ddl()))
        db.session.execute(
            text("INSERT INTO legacy_user_areas (user_id, area) VALUES (1, 'SUPIM')")
        )
        db.session.commit()

        assert criar_snapshots_legado()["legacy_user_areas"] == 3
        assert _contar("legacy_user_areas") == 3


def test_espelho_maior_que_a_origem_aborta(app) -> None:
    with app.app_context():
        _criar_user_areas([(1, "SUPIM")])
        espelho = next(e for e in _ESPELHOS_LEGADOS if e.destino == "legacy_user_areas")
        db.session.execute(text(espelho.ddl()))
        db.session.execute(
            text(
                "INSERT INTO legacy_user_areas (user_id, area) VALUES (1, 'X'), (2, 'Y')"
            )
        )
        db.session.commit()

        with pytest.raises(EspelhoLegadoInconsistente, match="legacy_user_areas"):
            criar_snapshots_legado()
        assert _contar("legacy_user_areas") == 2
