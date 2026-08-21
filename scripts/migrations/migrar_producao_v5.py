#!/usr/bin/env python3
"""Orquestrador da migração de produção (MySQL 8.0) para o schema v5.0.

Roda a migração em stages nomeados, na única ordem que funciona, em vez de dez
comandos manuais com dependência implícita entre eles. Dry-run por padrão:
nada é gravado sem ``--apply``. Cada stage é idempotente, imprime contagens
antes/depois e aborta com exit 1 quando falta uma pré-condição.

O ensaio (sem ``--apply``) roda todos os stages numa transação só e desfaz no
fim, de modo que um stage enxerga o que o anterior escreveu.

Uso:
    python3 scripts/migrations/migrar_producao_v5.py --all                 # ensaio
    python3 scripts/migrations/migrar_producao_v5.py --all --apply         # grava
    python3 scripts/migrations/migrar_producao_v5.py --stage colapso --apply

O passo Alembic (``stamp --purge a1b2c3d4e5f6`` + ``upgrade head``) NÃO está
aqui: é comando de deploy, documentado em docs/runbook-migracao-producao-v5.md.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Callable, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Os stages rodam com o schema ainda em transição: a verificação de boot mataria
# o processo antes do primeiro print.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from sqlalchemy import text  # noqa: E402

from app import app, db  # noqa: E402
from scripts.migrations.auditoria_role_map import (  # noqa: E402
    ConferenciaKeep,
    EstadoColapso,
    auditar,
    conferir_keep,
    desserializar_mapas,
    keep_esperado,
    montar_estado,
    motivo_da_reprovacao,
    pares_de_vinculo,
    resumo,
    serializar_mapas,
    serializar_vinculos,
    vinculos_atuais,
)

from scripts.migrations.relatorio_migracao import (  # noqa: E402
    Contexto,
    StageAbortado,
    atualizar_relatorio,
    exigir_role_map_pre,
    exigir_vinculos_pre,
    recusar_sobrescrever_a_base,
    registrar_stage,
)
from scripts.migrations.verificacao_schema import (  # noqa: E402
    colunas_faltando,
    indices_faltando,
    mensagem_schema,
    tabelas_existentes,
    tabelas_extra,
    tabelas_faltando,
)

RELATORIO_PADRAO = PROJECT_ROOT / "instance" / "migracao-producao-v5.json"

BACKFILLS_DADOS = (
    "scripts/migrations/backfill_task_assignees.py --apply",
    "scripts/migrations/backfill_etapa_responsaveis.py --apply",
    "scripts/migrations/backfill_sei_processes.py --apply",
    "scripts/migrations/backfill_cpf_govbr.py --apply",
    "scripts/migrations/elect_super_admin.py --apply",
    "scripts/migrations/encrypt_oauth_tokens.py --apply",
)


# Exceções das outras frentes que também são pré-condição violada, não bug: sem
# esta lista o segundo `--all --apply` saía com traceback de "ERRO INESPERADO".
ABORTOS_DE_DOMINIO: tuple[tuple[str, str], ...] = (
    ("scripts.migrations.backfill_orgaos", "ColapsoJaAplicado"),
    ("scripts.migrations.backfill_orgaos", "EspelhoLegadoInconsistente"),
    ("services.user_orgao_collapse", "ClosureNaoConstruidaError"),
)


def _carregar(modulo: str, atributo: str) -> object:
    """Importa `atributo` de `modulo`, virando abort acionável se faltar."""
    try:
        return getattr(importlib.import_module(modulo), atributo)
    except (ImportError, AttributeError) as exc:
        raise StageAbortado(
            f"{modulo}.{atributo} indisponível ({exc}). "
            "Este stage depende dessa frente; confira o deploy do código."
        ) from exc


def _contar(sql: str) -> int:
    return int(db.session.execute(text(sql)).scalar() or 0)


def _contagens_organograma() -> dict[str, int]:
    return {
        "orgao_tipo": _contar("SELECT COUNT(*) FROM orgao_tipo"),
        "orgao_unidade": _contar("SELECT COUNT(*) FROM orgao_unidade"),
        "orgao_closure": _contar("SELECT COUNT(*) FROM orgao_closure"),
    }


def _contagens_vinculos() -> dict[str, int]:
    return {
        "user_orgao": _contar("SELECT COUNT(*) FROM user_orgao"),
        "usuarios_vinculados": _contar(
            "SELECT COUNT(DISTINCT user_id) FROM user_orgao"
        ),
        "projetos_com_orgao": _contar(
            "SELECT COUNT(*) FROM project WHERE orgao_id IS NOT NULL"
        ),
    }


def _com_contagens(
    contar: Callable[[], dict[str, int]], executar: Callable[[], object]
) -> dict[str, object]:
    """Roda o stage entre duas leituras das mesmas contagens."""
    antes = contar()
    relatorio = executar()
    return {"antes": antes, "depois": contar(), "relatorio": _resumir(relatorio)}


def _resumir(relatorio: object) -> dict[str, object]:
    """Achata o relatório de outra frente sem depender do tipo concreto dela."""
    if is_dataclass(relatorio) and not isinstance(relatorio, type):
        return asdict(relatorio)
    return {"repr": repr(relatorio)}


def _tabelas_snapshot(existentes: set[str]) -> list[str]:
    """`legacy_*` fora do modelo: são as cópias deste stage, não tabelas do app."""
    return sorted(
        nome
        for nome in existentes
        if nome.startswith("legacy_") and nome not in db.metadata.tables
    )


def stage_snapshot(ctx: Contexto) -> dict[str, object]:
    """Congela as tabelas legadas em `legacy_*` antes da primeira escrita."""
    criar_snapshots_legado = _carregar(
        "scripts.migrations.backfill_orgaos", "criar_snapshots_legado"
    )
    antes = _tabelas_snapshot(tabelas_existentes())
    if not ctx.apply:
        return {"antes": antes, "depois": antes, "nota": "dry-run não copia nada"}
    linhas = criar_snapshots_legado()
    return {
        "antes": antes,
        "depois": _tabelas_snapshot(tabelas_existentes()),
        "linhas_copiadas": linhas,
    }


def stage_verificar_schema(ctx: Contexto) -> dict[str, object]:
    """Barra a migração enquanto o schema não estiver no head do código."""
    existentes = tabelas_existentes()
    tabelas = tabelas_faltando(existentes)
    colunas = colunas_faltando(existentes)
    indices = indices_faltando(existentes)
    if tabelas or colunas or indices:
        raise StageAbortado(mensagem_schema(tabelas, colunas, indices))
    return {
        "tabelas_no_modelo": len(db.metadata.tables),
        "tabelas_no_banco": len(existentes),
        "tabelas_extra_ignoradas": tabelas_extra(existentes),
    }


def _exigir_csv_do_organograma() -> None:
    """O CSV não vem do banco: se não subiu junto com o código, aborta antes."""
    caminho = Path(str(_carregar("scripts.catalog.organograma_siorg", "CSV_PADRAO")))
    if caminho.exists():
        return
    raise StageAbortado(
        f"CSV da estrutura do SIORG ausente: {caminho}. Copie "
        "catalogs/estrutura_setd_proderj.csv para o servidor e rode de novo."
    )


def stage_organograma(ctx: Contexto) -> dict[str, object]:
    """Importa a estrutura real do SIORG (SETD + PRODERJ) e refaz a closure."""
    importar = _carregar("scripts.catalog.organograma_siorg", "importar_estrutura")
    _exigir_csv_do_organograma()
    return _com_contagens(
        _contagens_organograma, lambda: importar(dry_run=not ctx.apply)
    )


def stage_backfill_orgaos(ctx: Contexto) -> dict[str, object]:
    """Converte area_catalog/user_areas em project.orgao_id e user_orgao."""
    backfill = _carregar("scripts.migrations.backfill_orgaos", "run_backfill_orgaos")
    return _com_contagens(_contagens_vinculos, lambda: backfill(dry_run=not ctx.apply))


def stage_snapshot_role_map(ctx: Contexto) -> dict[str, object]:
    """Grava no --relatorio o alcance de cada usuário ANTES do colapso."""
    snapshot_role_maps = _carregar("services.user_orgao_collapse", "snapshot_role_maps")
    recusar_sobrescrever_a_base(ctx)
    mapas = snapshot_role_maps()
    vinculos = vinculos_atuais()
    atualizar_relatorio(
        ctx.relatorio,
        {
            "role_map_pre": serializar_mapas(mapas),
            "vinculos_pre": serializar_vinculos(vinculos),
            # Snapshot de ensaio não serve de linha de base para o colapso real.
            "role_map_pre_aplicado": ctx.apply,
        },
    )
    return {
        "usuarios": len(mapas),
        "vinculos": sum(len(v) for v in vinculos.values()),
        "arquivo": str(ctx.relatorio),
    }


def stage_colapso(ctx: Contexto) -> dict[str, object]:
    """Poda genéricos e absorve descendentes; exige a linha de base ANTES."""
    colapsar = _carregar("services.user_orgao_collapse", "aplicar_colapso")
    exigir_role_map_pre(ctx)
    return _com_contagens(_contagens_vinculos, lambda: colapsar(dry_run=not ctx.apply))


def stage_verificar_role_map(ctx: Contexto) -> dict[str, object]:
    """Reexecuta o colapso sobre a linha de base e exige `user_orgao` idêntico."""
    estado = _estado_do_colapso(ctx)
    auditoria = auditar(estado, _conferir_keep(estado))
    for linha in auditoria.linhas():
        print(f"  {linha}")
    if not auditoria.aprovada:
        raise StageAbortado(motivo_da_reprovacao(auditoria))
    return resumo(auditoria)


def _estado_do_colapso(ctx: Contexto) -> EstadoColapso:
    snapshot_role_maps = _carregar("services.user_orgao_collapse", "snapshot_role_maps")
    siglas = _carregar("services.user_orgao_collapse", "SIGLAS_GENERICAS")
    return montar_estado(
        role_map_pre=desserializar_mapas(exigir_role_map_pre(ctx)),
        role_map_pos=snapshot_role_maps(),
        vinculos_pre=exigir_vinculos_pre(ctx),
        vinculos_pos=vinculos_atuais(),
        siglas_genericas=frozenset(siglas),
    )


def _conferir_keep(estado: EstadoColapso) -> ConferenciaKeep:
    """Veredito do portão: KEEP recalculado × `user_orgao` real, par a par."""
    calcular_colapso = _carregar("services.user_orgao_collapse", "calcular_colapso")
    rank_do_papel = _carregar("services.user_orgao_collapse", "rank_do_papel")
    esperado = keep_esperado(
        estado.vinculos_pre,
        estado.genericos,
        estado.ancestrais,
        calcular_colapso,
        rank_do_papel,
    )
    return conferir_keep(esperado, pares_de_vinculo(estado.vinculos_pos))


def stage_backfills_dados(ctx: Contexto) -> dict[str, object]:
    """Lista (sem executar) os one-shot restantes, na ordem em que devem rodar."""
    print("  rode, nesta ordem, com a venv de produção:")
    for posicao, comando in enumerate(BACKFILLS_DADOS, start=1):
        print(f"    {posicao}. python3 {comando}")
    print("  cada um aceita dry-run: basta omitir --apply.")
    return {"comandos_listados": len(BACKFILLS_DADOS), "executados": 0}


# runner ---


STAGES: dict[str, Callable[[Contexto], dict[str, object]]] = {
    "snapshot": stage_snapshot,
    "verificar_schema": stage_verificar_schema,
    "organograma": stage_organograma,
    "backfill_orgaos": stage_backfill_orgaos,
    "snapshot_role_map": stage_snapshot_role_map,
    "colapso": stage_colapso,
    "verificar_role_map": stage_verificar_role_map,
    "backfills_dados": stage_backfills_dados,
}

ORDEM: tuple[str, ...] = tuple(STAGES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    alvo = parser.add_mutually_exclusive_group(required=True)
    alvo.add_argument(
        "--stage",
        action="append",
        choices=ORDEM,
        help="Stage a rodar (repetível). A ordem canônica é sempre respeitada.",
    )
    alvo.add_argument("--all", action="store_true", help="Roda todos os stages.")
    parser.add_argument(
        "--apply", action="store_true", help="Grava. Sem esta flag é dry-run."
    )
    parser.add_argument(
        "--relatorio",
        default=str(RELATORIO_PADRAO),
        help=f"JSON de saída/entrada dos stages (padrão: {RELATORIO_PADRAO}).",
    )
    return parser.parse_args()


def _stages_pedidos(args: argparse.Namespace) -> list[str]:
    if args.all:
        return list(ORDEM)
    pedidos = set(args.stage or [])
    return [nome for nome in ORDEM if nome in pedidos]


def _executar(nome: str, ctx: Contexto) -> None:
    print(f"\n=== {nome} {'[APLICANDO]' if ctx.apply else '[dry-run]'}")
    dados = STAGES[nome](ctx)
    for chave, valor in dados.items():
        _imprimir(chave, valor)
    registrar_stage(ctx.relatorio, nome, dados)
    print(f"  registrado em: {ctx.relatorio}")


def _imprimir(chave: str, valor: object) -> None:
    """Imprime um par do stage; relatório grande vira as linhas do seu `resumo`."""
    linhas = _linhas_de_resumo(valor)
    if linhas is None:
        print(f"  {chave}: {valor}")
        return
    print(f"  {chave}:")
    for linha in linhas:
        print(f"    {linha}")


def _linhas_de_resumo(valor: object) -> list[str] | None:
    """As linhas legíveis de um relatório achatado, ou None se não houver."""
    if not isinstance(valor, dict):
        return None
    resumo = valor.get("resumo")
    if not isinstance(resumo, (list, tuple)) or not resumo:
        return None
    return [str(linha) for linha in resumo]


def _cabecalho(ctx: Contexto) -> None:
    print(f"banco: {db.engine.url.render_as_string(hide_password=True)}")
    print(f"dialeto: {db.engine.dialect.name} · relatório: {ctx.relatorio}")
    if not ctx.apply:
        print(
            "MODO DRY-RUN: nada será gravado. Os stages rodam em UMA transação "
            "só e o rollback é no fim, então cada stage enxerga o anterior."
        )


def _sem_efeito() -> None:
    """Substitui `rollback` durante o ensaio: quem desfaz é o `finally`."""


@contextmanager
def _ensaio_em_uma_transacao(ctx: Contexto) -> Iterator[None]:
    """Dry-run inteiro numa transação só, para os stages se enxergarem.

    Com rollback por stage, o `--all` em dry-run rodava o backfill contra a
    árvore que o stage anterior desfez (1231 projetos sem match) e fotografava
    67 role maps vazios, com exit 0. Aqui `commit` vira `flush` e `rollback`
    vira no-op até o `finally` — e nenhum stage emite DDL em dry-run.
    """
    if ctx.apply:
        yield
        return
    sessao = db.session()
    commit, rollback = sessao.commit, sessao.rollback
    sessao.commit, sessao.rollback = sessao.flush, _sem_efeito
    try:
        yield
    finally:
        sessao.commit, sessao.rollback = commit, rollback
        sessao.rollback()


def _classes_de_aborto() -> tuple[type[BaseException], ...]:
    """`StageAbortado` mais as exceções de domínio que estiverem importáveis."""
    classes: list[type[BaseException]] = [StageAbortado]
    for modulo, nome in ABORTOS_DE_DOMINIO:
        try:
            classes.append(getattr(importlib.import_module(modulo), nome))
        except (ImportError, AttributeError):
            continue
    return tuple(classes)


def _rodar(nomes: list[str], ctx: Contexto) -> int:
    abortos = _classes_de_aborto()
    for nome in nomes:
        try:
            _executar(nome, ctx)
        except abortos as exc:
            db.session.rollback()
            print(f"\nERRO [{nome}] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            db.session.rollback()
            print(
                f"\nERRO INESPERADO no stage `{nome}`: {exc!r}. O que cada stage "
                f"já fez está em {ctx.relatorio}.",
                file=sys.stderr,
            )
            raise
    print("\nOK: stages concluídos.")
    return 0


def main() -> int:
    args = parse_args()
    ctx = Contexto(apply=args.apply, relatorio=Path(args.relatorio))
    with app.app_context():
        _cabecalho(ctx)
        with _ensaio_em_uma_transacao(ctx):
            return _rodar(_stages_pedidos(args), ctx)


if __name__ == "__main__":
    raise SystemExit(main())
