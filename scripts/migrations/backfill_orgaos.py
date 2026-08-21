#!/usr/bin/env python3
"""Backfill de vinculos de orgao a partir das areas legadas (SQL puro).

Converte o modelo flat (`area_catalog` / `user_areas` / `project.area_responsavel`)
para o hierarquico (`project.orgao_id` + `user_orgao`). Este passo **nao cria
orgao**: a arvore real vem do SIORG via `scripts/catalog/organograma_siorg.py`, e
sigla legada sem unidade correspondente so aparece em `unmatched` — criar unidade
nova aqui deixaria a arvore plana e o colapso de
`services/user_orgao_collapse.py` nao derrubaria nada.

Tudo em SQL puro (nada de ORM `OrgaoUnidade`): o modelo declara
`tipo_ref = relationship("OrgaoTipo", lazy="joined")`, entao qualquer query ORM
emite LEFT JOIN em `orgao_tipo` — tabela ausente no banco legado.

Runbook: `--snapshot` (antes do drop das tabelas legadas) -> migrations e
importacao do organograma SIORG -> execucao sem flag (dry-run) -> `--apply`.
Os espelhos `legacy_*` deixam o backfill rodar DEPOIS do drop. Idempotente:
rodar 2x nao duplica linhas.

Trava: depois do colapso de `services/user_orgao_collapse.py` o backfill ABORTA
(`ColapsoJaAplicado`). A fonte legada continua com todas as areas, entao
reinserir aqui recriaria os vinculos podados e desfaria o colapso em silencio.
Duas evidencias disparam a trava, nesta ordem:

1. a marca duravel `legacy_user_orgao_pre_colapso` — espelho de `user_orgao`
   que `snapshot_user_orgao_pre_colapso()` grava a pedido do colapso, e que
   tambem serve de backup para restaurar os vinculos podados;
2. sem a marca, a assinatura da poda: vinculos legados que voltariam para
   usuarios que JA tem vinculo (numa migracao honesta isso e sempre vazio).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import current_app
from sqlalchemy import bindparam, inspect, text

from models import db

# Papel herdado por todo vinculo legado: `user_areas` nao tinha papel, e
# `services.authorization._vinculo_rank` ja trata papel ausente como gestor.
PAPEL_HERDADO = "gestor"

FONTE_INDISPONIVEL = "(indisponivel)"

# Espelho de `user_orgao` gravado ANTES da poda: e backup e, ao mesmo tempo, a
# marca duravel de que o colapso ja rodou neste banco.
TABELA_PRE_COLAPSO = "legacy_user_orgao_pre_colapso"

RUNBOOK = "docs/runbook-migracao-producao-v5.md"


class ColapsoJaAplicado(RuntimeError):
    """O colapso de `user_orgao` ja rodou: reprocessar o backfill o desfaria."""


class EspelhoLegadoInconsistente(RuntimeError):
    """Espelho `legacy_*` maior que a origem — nao e backup deste banco."""


@dataclass(frozen=True)
class _EspelhoLegado:
    """Copia congelada de uma tabela/coluna legada antes do drop.

    `colunas` sao triplas `(coluna_origem, coluna_destino, tipo_sql)`; o tipo e
    escrito em SQL aceito por SQLite e MySQL.
    """

    destino: str
    origem: str
    coluna_exigida: str
    colunas: tuple[tuple[str, str, str], ...]

    def ddl(self) -> str:
        campos = ", ".join(
            f"{destino} {tipo} NOT NULL" for _, destino, tipo in self.colunas
        )
        return f"CREATE TABLE IF NOT EXISTS {self.destino} ({campos})"

    def copia(self) -> str:
        destinos = ", ".join(destino for _, destino, _ in self.colunas)
        origens = ", ".join(origem for origem, _, _ in self.colunas)
        return (
            f"INSERT INTO {self.destino} ({destinos}) SELECT {origens} "
            f"FROM {self.origem} WHERE {self.coluna_exigida} IS NOT NULL"
        )


_TEXTO = "VARCHAR(255)"

_ESPELHOS_LEGADOS: tuple[_EspelhoLegado, ...] = (
    _EspelhoLegado(
        destino="legacy_user_areas",
        origem="user_areas",
        coluna_exigida="area",
        colunas=(("user_id", "user_id", "INTEGER"), ("area", "area", _TEXTO)),
    ),
    _EspelhoLegado(
        destino="legacy_area_catalog",
        origem="area_catalog",
        coluna_exigida="name",
        colunas=(("name", "name", _TEXTO),),
    ),
    _EspelhoLegado(
        destino="legacy_project_area",
        origem="project",
        coluna_exigida="area_responsavel",
        colunas=(
            ("id", "project_id", "INTEGER"),
            ("area_responsavel", "area_responsavel", _TEXTO),
        ),
    ),
    # `user.area_responsavel` nao e lido por nenhuma migration nem por este
    # backfill; o espelho existe so para nao perder os 28 valores no drop.
    _EspelhoLegado(
        destino="legacy_user_area_responsavel",
        origem="user",
        coluna_exigida="area_responsavel",
        colunas=(
            ("id", "user_id", "INTEGER"),
            ("area_responsavel", "area_responsavel", _TEXTO),
        ),
    ),
)


@dataclass
class BackfillReport:
    """Contagens e siglas sem correspondencia de uma execucao do backfill."""

    dry_run: bool = True
    fonte_projetos: str = FONTE_INDISPONIVEL
    fonte_user_areas: str = FONTE_INDISPONIVEL
    projects_linked: int = 0
    projects_sem_orgao: int = 0
    projects_unmatched: list[str] = field(default_factory=list)
    projects_unmatched_rows: int = 0
    user_orgaos_linked: int = 0
    user_orgaos_existentes: int = 0
    user_areas_unmatched: list[str] = field(default_factory=list)
    user_areas_unmatched_rows: int = 0
    catalogo_sem_orgao: list[str] = field(default_factory=list)

    def linhas(self) -> list[str]:
        """Resumo legivel, uma metrica por linha."""
        return [
            f"dry_run={self.dry_run}",
            f"fonte projetos={self.fonte_projetos} · fonte areas de usuario={self.fonte_user_areas}",
            f"projetos com orgao_id setado: {self.projects_linked}",
            f"projetos ainda sem orgao_id: {self.projects_sem_orgao}",
            f"vinculos user_orgao criados: {self.user_orgaos_linked} "
            f"(ja existentes: {self.user_orgaos_existentes})",
            f"siglas sem unidade SIORG — catalogo: {self.catalogo_sem_orgao} · "
            f"projetos ({self.projects_unmatched_rows}): {self.projects_unmatched} · "
            f"user_areas ({self.user_areas_unmatched_rows}): {self.user_areas_unmatched}",
        ]

    def log(self) -> None:
        for linha in self.linhas():
            current_app.logger.info("[backfill_orgaos] %s", linha)


def normalizar_sigla(bruto: object) -> str:
    """TRIM + colapso de espacos + UPPER. Ex.: ` supim ` -> `SUPIM`.

    Normalizar em Python (nunca `func.lower` no SQL): a colacao
    `utf8mb4_0900_ai_ci` do MySQL e case E accent-insensitive e mudaria o
    resultado do casamento em relacao ao SQLite.
    """
    if bruto is None:
        return ""
    return " ".join(str(bruto).strip().split()).upper()


def _tabelas() -> set[str]:
    return set(inspect(db.engine).get_table_names())


def _colunas(tabela: str) -> set[str]:
    if tabela not in _tabelas():
        return set()
    return {coluna["name"] for coluna in inspect(db.engine).get_columns(tabela)}


def _contar(tabela: str, filtro: str = "") -> int:
    where = f" WHERE {filtro}" if filtro else ""
    return int(
        db.session.execute(text(f"SELECT COUNT(*) FROM {tabela}{where}")).scalar() or 0
    )


def _exigir_espelho_nao_maior(
    espelho: _EspelhoLegado, copiadas: int, origem: int
) -> None:
    if copiadas <= origem:
        return
    raise EspelhoLegadoInconsistente(
        f"{espelho.destino} tem {copiadas} linha(s) e {espelho.origem} tem apenas "
        f"{origem} com {espelho.coluna_exigida} NOT NULL: o espelho nao e deste "
        "banco. Recopiar apagaria o backup maior — confira a origem e remova o "
        "espelho a mao se ele for lixo de outro ensaio."
    )


def _criar_espelho(espelho: _EspelhoLegado) -> int:
    """Cria e popula um espelho legado. Retorna as linhas copiadas.

    Espelho PARCIAL (ensaio anterior interrompido) e refeito do zero: ter
    qualquer linha nao prova backup completo, e `c5f8a1b2d9e0` dropa a origem
    logo depois confiando neste espelho.
    """
    if espelho.coluna_exigida not in _colunas(espelho.origem):
        return 0
    db.session.execute(text(espelho.ddl()))
    na_origem = _contar(espelho.origem, f"{espelho.coluna_exigida} IS NOT NULL")
    copiadas = _contar(espelho.destino)
    if copiadas == na_origem:
        return 0
    _exigir_espelho_nao_maior(espelho, copiadas, na_origem)
    db.session.execute(text(f"DELETE FROM {espelho.destino}"))
    return int(db.session.execute(text(espelho.copia())).rowcount or 0)


def criar_snapshots_legado() -> dict[str, int]:
    """Congela as tabelas/colunas legadas de area em espelhos `legacy_*`.

    Rodar ANTES do drop das tabelas legadas. Idempotente: espelho completo nao
    e recopiado, espelho parcial e refeito e origem inexistente e ignorada.

    Ex.: ``criar_snapshots_legado()`` ->
    ``{"legacy_user_areas": 218, "legacy_area_catalog": 38, ...}``
    """
    copiadas = {esp.destino: _criar_espelho(esp) for esp in _ESPELHOS_LEGADOS}
    db.session.commit()
    return copiadas


# Fontes de cada area legada, na ordem de preferencia: origem viva primeiro,
# espelho `legacy_*` depois (o backfill roda igual antes ou depois do drop).
_FONTES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "projeto": (
        (
            "project",
            "area_responsavel",
            "SELECT id, area_responsavel FROM project WHERE area_responsavel IS NOT NULL",
        ),
        (
            "legacy_project_area",
            "area_responsavel",
            "SELECT project_id, area_responsavel FROM legacy_project_area",
        ),
    ),
    "usuario": (
        ("user_areas", "area", "SELECT user_id, area FROM user_areas"),
        ("legacy_user_areas", "area", "SELECT user_id, area FROM legacy_user_areas"),
    ),
    "catalogo": (
        ("area_catalog", "name", "SELECT name FROM area_catalog"),
        ("legacy_area_catalog", "name", "SELECT name FROM legacy_area_catalog"),
    ),
}


def _fonte(chave: str) -> tuple[str, str] | None:
    """Primeira fonte disponivel de `_FONTES[chave]` -> `(tabela, sql)`."""
    for tabela, coluna, sql in _FONTES[chave]:
        if coluna in _colunas(tabela):
            return tabela, sql
    return None


def _pares_normalizados(sql: str) -> list[tuple[int, str]]:
    linhas = db.session.execute(text(sql)).all()
    pares = ((linha[0], normalizar_sigla(linha[1])) for linha in linhas)
    return [
        (int(chave), sigla) for chave, sigla in pares if chave is not None and sigla
    ]


def _valores_normalizados(sql: str) -> list[str]:
    linhas = db.session.execute(text(sql)).all()
    return [
        sigla for sigla in (normalizar_sigla(linha[0]) for linha in linhas) if sigla
    ]


@dataclass(frozen=True)
class _AreasLegadas:
    fonte_projetos: str
    pares_projeto: list[tuple[int, str]]
    fonte_usuarios: str
    pares_usuario: list[tuple[int, str]]
    catalogo: list[str]

    @property
    def siglas(self) -> set[str]:
        return (
            {sigla for _, sigla in self.pares_projeto}
            | {sigla for _, sigla in self.pares_usuario}
            | set(self.catalogo)
        )


def _carregar_areas_legadas() -> _AreasLegadas:
    """Le as areas legadas da origem viva ou, se ja dropada, do espelho."""
    projetos = _fonte("projeto")
    usuarios = _fonte("usuario")
    catalogo = _fonte("catalogo")
    return _AreasLegadas(
        fonte_projetos=projetos[0] if projetos else FONTE_INDISPONIVEL,
        pares_projeto=_pares_normalizados(projetos[1]) if projetos else [],
        fonte_usuarios=usuarios[0] if usuarios else FONTE_INDISPONIVEL,
        pares_usuario=_pares_normalizados(usuarios[1]) if usuarios else [],
        catalogo=_valores_normalizados(catalogo[1]) if catalogo else [],
    )


def mapear_siglas(
    siglas: set[str],
    *,
    alias_sigla: dict[str, int],
    vinculos_duplos: dict[str, tuple[int, int]],
    orgao_por_codigo: dict[int, int],
) -> dict[str, tuple[int, ...]]:
    """Sigla legada normalizada -> ids de `orgao_unidade` (funcao pura).

    Siglas de vinculo duplo (`GAR/GFS`) rendem DOIS ids. Sigla cujo codigo
    SIORG nao esta importado fica de fora do mapa (vira unmatched no relatorio).

    Ex.: ``mapear_siglas({"SUPIM"}, alias_sigla={"SUPIM": 12},
    vinculos_duplos={}, orgao_por_codigo={12: 7})`` -> ``{"SUPIM": (7,)}``
    """
    codigos_por_sigla: dict[str, tuple[int, ...]] = {
        normalizar_sigla(sigla): (codigo,) for sigla, codigo in alias_sigla.items()
    }
    codigos_por_sigla.update(
        {normalizar_sigla(sigla): tuple(par) for sigla, par in vinculos_duplos.items()}
    )
    resolvido: dict[str, tuple[int, ...]] = {}
    for sigla in siglas:
        codigos = codigos_por_sigla.get(sigla, ())
        ids = tuple(orgao_por_codigo[c] for c in codigos if c in orgao_por_codigo)
        if codigos and len(ids) == len(codigos):
            resolvido[sigla] = ids
    return resolvido


def _mapear_com_organograma(siglas: set[str]) -> dict[str, tuple[int, ...]]:
    # Import tardio: o organograma so precisa estar importavel na hora de rodar.
    from scripts.catalog.organograma_siorg import (
        ALIAS_SIGLA_LEGADA,
        VINCULOS_DUPLOS,
        resolver_orgao_id_por_codigo,
    )

    return mapear_siglas(
        siglas,
        alias_sigla=ALIAS_SIGLA_LEGADA,
        vinculos_duplos=VINCULOS_DUPLOS,
        orgao_por_codigo=resolver_orgao_id_por_codigo(),
    )


def _aplicar_orgao_em_projetos(ids_por_orgao: dict[int, list[int]]) -> int:
    comando = text(
        "UPDATE project SET orgao_id = :orgao_id "
        "WHERE orgao_id IS NULL AND id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    atualizados = 0
    for orgao_id, project_ids in ids_por_orgao.items():
        resultado = db.session.execute(
            comando, {"orgao_id": orgao_id, "ids": project_ids}
        )
        atualizados += int(resultado.rowcount or 0)
    return atualizados


def _vincular_projetos(
    pares: list[tuple[int, str]],
    mapa: dict[str, tuple[int, ...]],
    report: BackfillReport,
) -> None:
    ids_por_orgao: dict[int, list[int]] = defaultdict(list)
    sem_match: Counter[str] = Counter()
    for project_id, sigla in pares:
        alvos = mapa.get(sigla)
        if not alvos:
            sem_match[sigla] += 1
            continue
        # Sigla de vinculo duplo: o dono do projeto e a primeira unidade do par.
        ids_por_orgao[alvos[0]].append(project_id)
    report.projects_linked = _aplicar_orgao_em_projetos(ids_por_orgao)
    report.projects_unmatched = sorted(sem_match)
    report.projects_unmatched_rows = sum(sem_match.values())


def _pares_user_orgao_existentes() -> set[tuple[int, int]]:
    linhas = db.session.execute(text("SELECT user_id, orgao_id FROM user_orgao")).all()
    return {(int(linha[0]), int(linha[1])) for linha in linhas}


def _inserir_user_orgaos(pares: list[tuple[int, int]]) -> int:
    if not pares:
        return 0
    # `papel` explicito: com strict mode o MySQL rejeita a coluna NOT NULL
    # omitida (ERROR 1364) mesmo havendo server_default.
    db.session.execute(
        text(
            "INSERT INTO user_orgao (user_id, orgao_id, papel) "
            "VALUES (:user_id, :orgao_id, :papel)"
        ),
        [
            {"user_id": user_id, "orgao_id": orgao_id, "papel": PAPEL_HERDADO}
            for user_id, orgao_id in pares
        ],
    )
    return len(pares)


def _exigir_coluna_papel() -> None:
    colunas = _colunas("user_orgao")
    if "papel" in colunas:
        return
    raise RuntimeError(
        "user_orgao sem coluna `papel`; colunas encontradas: "
        f"{sorted(colunas)}. Esperado o schema do head (user_id, orgao_id, papel)."
    )


def _vincular_usuarios(
    pares: list[tuple[int, str]],
    mapa: dict[str, tuple[int, ...]],
    report: BackfillReport,
) -> None:
    _exigir_coluna_papel()
    sem_match: Counter[str] = Counter()
    desejados: set[tuple[int, int]] = set()
    for user_id, sigla in pares:
        alvos = mapa.get(sigla)
        if not alvos:
            sem_match[sigla] += 1
            continue
        desejados.update((user_id, orgao_id) for orgao_id in alvos)
    existentes = _pares_user_orgao_existentes()
    report.user_orgaos_existentes = len(desejados & existentes)
    report.user_orgaos_linked = _inserir_user_orgaos(sorted(desejados - existentes))
    report.user_areas_unmatched = sorted(sem_match)
    report.user_areas_unmatched_rows = sum(sem_match.values())


def snapshot_user_orgao_pre_colapso() -> int:
    """Congela `user_orgao` em `legacy_user_orgao_pre_colapso` e marca o colapso.

    Chamar de `services.user_orgao_collapse.aplicar_colapso(dry_run=False)`
    ANTES do DELETE: a tabela e o backup para restaurar os vinculos podados e a
    marca que faz este backfill abortar em vez de recria-los.
    Idempotente: espelho ja gravado nao e recopiado.

    Ex.: ``snapshot_user_orgao_pre_colapso()`` -> ``208``.
    """
    db.session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {TABELA_PRE_COLAPSO} "
            "(user_id INTEGER NOT NULL, orgao_id INTEGER NOT NULL, "
            f"papel {_TEXTO} NULL)"
        )
    )
    if _contar(TABELA_PRE_COLAPSO):
        return 0
    db.session.execute(
        text(
            f"INSERT INTO {TABELA_PRE_COLAPSO} (user_id, orgao_id, papel) "
            "SELECT user_id, orgao_id, papel FROM user_orgao"
        )
    )
    return _contar(TABELA_PRE_COLAPSO)


def _marca_pre_colapso_presente() -> bool:
    return TABELA_PRE_COLAPSO in _tabelas() and _contar(TABELA_PRE_COLAPSO) > 0


def _reinsercoes_em_usuarios_vinculados(
    pares_usuario: list[tuple[int, str]], mapa: dict[str, tuple[int, ...]]
) -> set[tuple[int, int]]:
    """Vinculos que voltariam para quem JA tem vinculo — assinatura da poda.

    Primeira execucao: o usuario ainda nao tem linha nenhuma, entao nada aqui.
    Segunda execucao honesta: o desejado ja existe, entao nada aqui tambem. So
    sobra o caso em que alguem removeu linhas de `user_orgao` sem mexer na fonte
    legada — que e exatamente o que o colapso faz.
    """
    existentes = _pares_user_orgao_existentes()
    ja_vinculados = {user_id for user_id, _ in existentes}
    desejados = {
        (user_id, orgao_id)
        for user_id, sigla in pares_usuario
        for orgao_id in mapa.get(sigla, ())
    }
    return {par for par in desejados - existentes if par[0] in ja_vinculados}


def _motivo_de_bloqueio(
    pares_usuario: list[tuple[int, str]], mapa: dict[str, tuple[int, ...]]
) -> str | None:
    """Evidencia de que o colapso ja rodou, ou None se o backfill pode seguir."""
    if _marca_pre_colapso_presente():
        return f"a marca `{TABELA_PRE_COLAPSO}` esta presente"
    reinsercoes = _reinsercoes_em_usuarios_vinculados(pares_usuario, mapa)
    if not reinsercoes:
        return None
    usuarios = sorted({user_id for user_id, _ in reinsercoes})
    return (
        f"{len(reinsercoes)} vinculo(s) legado(s) voltariam para {len(usuarios)} "
        f"usuario(s) que ja tem vinculo (user_id {usuarios[:5]}...)"
    )


def _exigir_colapso_nao_aplicado(
    pares_usuario: list[tuple[int, str]], mapa: dict[str, tuple[int, ...]]
) -> None:
    """Aborta se o colapso ja rodou — reinserir aqui desfaria a poda em silencio."""
    if "user_orgao" not in _tabelas():
        return
    motivo = _motivo_de_bloqueio(pares_usuario, mapa)
    if motivo is None:
        return
    raise ColapsoJaAplicado(
        f"O colapso de vinculos ja rodou neste banco: {motivo}. Seguir recriaria "
        "a partir de legacy_user_areas os vinculos podados, desfazendo o colapso "
        "em silencio. Para reprocessar do zero: restaure `user_orgao` a partir de "
        f"`{TABELA_PRE_COLAPSO}` (ou do backup), remova essa tabela e rode "
        f"backfill -> snapshot_role_map -> colapso na ordem do runbook ({RUNBOOK})."
    )


def _contar_projetos_sem_orgao() -> int:
    if "orgao_id" not in _colunas("project"):
        return 0
    return int(
        db.session.execute(
            text("SELECT COUNT(*) FROM project WHERE orgao_id IS NULL")
        ).scalar()
        or 0
    )


def _encerrar_transacao(dry_run: bool) -> None:
    if dry_run:
        db.session.rollback()
        return
    db.session.commit()


def run_backfill_orgaos(*, dry_run: bool = True) -> BackfillReport:
    """Liga projetos e usuarios as unidades SIORG. Requer app_context ativo.

    Nao cria orgao e nao cria snapshot: a arvore vem de
    `scripts/catalog/organograma_siorg.py` e o congelamento das tabelas legadas
    e o passo separado `criar_snapshots_legado()`. Levanta `ColapsoJaAplicado`
    quando o colapso ja rodou (rodar depois dele recriaria os vinculos podados).

    Ex.: ``run_backfill_orgaos(dry_run=False).projects_linked`` -> ``1231``.
    """
    report = BackfillReport(dry_run=dry_run)
    if "orgao_unidade" not in _tabelas():
        current_app.logger.warning(
            "[backfill_orgaos] tabela orgao_unidade nao existe; rodar as migrations antes."
        )
        return report

    areas = _carregar_areas_legadas()
    report.fonte_projetos = areas.fonte_projetos
    report.fonte_user_areas = areas.fonte_usuarios
    mapa = _mapear_com_organograma(areas.siglas)
    report.catalogo_sem_orgao = sorted(set(areas.catalogo) - set(mapa))
    _exigir_colapso_nao_aplicado(areas.pares_usuario, mapa)

    if "orgao_id" in _colunas("project"):
        _vincular_projetos(areas.pares_projeto, mapa, report)
    if "user_orgao" in _tabelas():
        _vincular_usuarios(areas.pares_usuario, mapa, report)
    report.projects_sem_orgao = _contar_projetos_sem_orgao()

    _encerrar_transacao(dry_run)
    report.log()
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Liga project.orgao_id e user_orgao as unidades SIORG."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava as alteracoes (default e dry-run, que so relata contagens).",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="So congela as tabelas legadas em legacy_* (rodar antes do drop).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    # Backfill de dados puro: importar o app nao deve rodar init/verificacao de schema.
    os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")
    from app import app

    with app.app_context():
        print(f"Banco: {app.config['SQLALCHEMY_DATABASE_URI']}")
        if args.snapshot:
            for tabela, linhas in criar_snapshots_legado().items():
                print(f"  {tabela}: {linhas} linhas copiadas")
            return 0
        report = run_backfill_orgaos(dry_run=not args.apply)
        print("\n".join(f"  {linha}" for linha in report.linhas()))
        if not args.apply:
            print("\nDry-run: nada gravado. Use --apply para gravar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
