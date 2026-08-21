"""Diferença entre o schema do código (metadata) e o do banco em migração.

Só leitura e comparação: quem transforma o resultado em abort é o stage
``verificar_schema`` do orquestrador (``migrar_producao_v5.py``).

Uso::

    faltando = tabelas_faltando(tabelas_existentes())
"""

from __future__ import annotations

from sqlalchemy import inspect

from models import db

# Revisão em que o banco legado precisa estar carimbado antes do upgrade.
REVISAO_ESPERADA_PRE = "a1b2c3d4e5f6"

COLUNAS_CRITICAS: dict[str, tuple[str, ...]] = {
    "orgao_unidade": (
        "tipo_id",
        "codigo_externo",
        "data_inicio_vigencia",
        "data_fim_vigencia",
    ),
    "siorg_sync_log": ("usuarios_escopo_zerado",),
    "task_comment": ("mentions",),
    "user": ("is_super_admin", "deleted_at"),
    "user_orgao": ("papel",),
}

INDICES_CRITICOS: dict[str, tuple[str, ...]] = {
    "etapa": ("ix_etapa_entry_type",),
    "user": ("ix_user_deleted_at",),
    "orgao_unidade": ("ix_orgao_unidade_tipo_id", "ix_orgao_unidade_codigo_externo"),
}

# Tabelas do dump legado sem modelo correspondente: ficam quietas, não são gap.
TABELAS_LEGADAS_TOLERADAS = frozenset(
    {"caderno_block", "caderno_state", "alembic_version", "area_catalog", "user_areas"}
)


def tabelas_existentes() -> set[str]:
    return set(inspect(db.engine).get_table_names())


def tabelas_faltando(existentes: set[str]) -> list[str]:
    return sorted(set(db.metadata.tables) - existentes)


def colunas_faltando(existentes: set[str]) -> dict[str, list[str]]:
    inspector = inspect(db.engine)
    faltando: dict[str, list[str]] = {}
    for tabela, colunas in COLUNAS_CRITICAS.items():
        if tabela not in existentes:
            continue
        presentes = {col["name"] for col in inspector.get_columns(tabela)}
        ausentes = [nome for nome in colunas if nome not in presentes]
        if ausentes:
            faltando[tabela] = ausentes
    return faltando


def indices_faltando(existentes: set[str]) -> dict[str, list[str]]:
    inspector = inspect(db.engine)
    faltando: dict[str, list[str]] = {}
    for tabela, indices in INDICES_CRITICOS.items():
        if tabela not in existentes:
            continue
        presentes = {idx["name"] for idx in inspector.get_indexes(tabela)}
        ausentes = [nome for nome in indices if nome not in presentes]
        if ausentes:
            faltando[tabela] = ausentes
    return faltando


def tabelas_extra(existentes: set[str]) -> list[str]:
    extras = existentes - set(db.metadata.tables) - TABELAS_LEGADAS_TOLERADAS
    return sorted(nome for nome in extras if not nome.startswith("legacy_"))


def mensagem_schema(
    tabelas: list[str], colunas: dict[str, list[str]], indices: dict[str, list[str]]
) -> str:
    """Aborta ensinando o comando exato do passo 4 do runbook."""
    return (
        f"schema incompleto — tabelas faltando: {tabelas or 'nenhuma'}; "
        f"colunas faltando: {colunas or 'nenhuma'}; "
        f"índices faltando: {indices or 'nenhum'}. "
        f"Rode `flask db stamp --purge {REVISAO_ESPERADA_PRE}` e depois "
        "`flask db upgrade head` (passo 4 do runbook) antes de seguir."
    )
