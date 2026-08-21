"""Verificação de schema no boot (Sprint 5.3).

O boot NÃO roda mais migração nenhuma: DDL vem de ``alembic upgrade head``
(passo explícito de deploy) e mutações de dados viram comandos CLI em
``scripts/migrations/``. Aqui só se compara o ``alembic_version`` do banco com
o head de ``migrations/versions`` — divergência derruba o processo com
instrução acionável, em vez de N workers gunicorn aplicarem DDL sem lock.

A comparação de string não basta: um banco legado carimbado no head responde
o head e sobe com 12 tabelas faltando — a quebra só apareceria no primeiro
request. Por isso há também uma verificação ESTRUTURAL (tabelas de
``db.metadata`` ausentes + colunas ausentes nas tabelas críticas).

Escape de emergência: ``SKIP_SCHEMA_CHECK=1`` pula a verificação (documentado
no README; usar só para subir uma instância enquanto se corrige o banco).
"""

import os
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from models import db

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Revisão que corresponde ao schema do banco legado de produção (pré-baseline).
# Carimbar `head` nele faria o `upgrade` seguinte virar no-op permanente — o
# banco ficaria sem a DDL das revisões b2c4d6e8f0a1..0257819cbe43.
_REVISAO_LEGADO_PRE_BASELINE = "a1b2c3d4e5f6"
_RUNBOOK = "docs/runbook-migracao-producao-v5.md"

# Tabelas cujo diff de colunas é conferido no boot: são as que toda requisição
# autenticada toca (sessão, escopo por órgão e as três entidades do domínio).
_TABELAS_CRITICAS: tuple[str, ...] = (
    "user",
    "user_orgao",
    "orgao_unidade",
    "project",
    "task",
    "etapa",
)


class SchemaVersionMismatch(RuntimeError):
    """Banco fora do head do Alembic — o boot deve falhar alto."""


def _alembic_script_directory():
    """ScriptDirectory de ``migrations/`` (cadeia de revisões do repositório)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config)


def alembic_head_revision() -> str:
    """Head único do ScriptDirectory em ``migrations/`` (ex.: ``'ab12cd34ef56'``)."""
    return _alembic_script_directory().get_current_head()


def _revisao_existe_na_cadeia(revision: str) -> bool:
    """True se ``revision`` é resolvível na cadeia atual (False = stamp órfão)."""
    try:
        return _alembic_script_directory().get_revision(revision) is not None
    except Exception:
        return False


def database_schema_revision() -> str | None:
    """``alembic_version`` do banco conectado; None se a tabela não existe/está vazia."""
    if not inspect(db.engine).has_table("alembic_version"):
        return None
    try:
        return db.session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    except SQLAlchemyError:
        return None


def _colunas_ausentes(inspector, tabelas_existentes: set[str]) -> list[str]:
    """``['user.deleted_at', …]`` — colunas do modelo ausentes nas tabelas críticas."""
    ausentes: list[str] = []
    for nome in _TABELAS_CRITICAS:
        tabela = db.metadata.tables.get(nome)
        if tabela is None or nome not in tabelas_existentes:
            continue
        no_banco = {coluna["name"] for coluna in inspector.get_columns(nome)}
        ausentes.extend(
            f"{nome}.{coluna.name}"
            for coluna in tabela.columns
            if coluna.name not in no_banco
        )
    return sorted(ausentes)


def _mensagem_schema_incompleto(tabelas: list[str], colunas: list[str]) -> str:
    """Mensagem acionável listando exatamente o que falta no banco."""
    faltas = []
    if tabelas:
        faltas.append(f"{len(tabelas)} tabela(s) [{', '.join(tabelas)}]")
    if colunas:
        faltas.append(f"{len(colunas)} coluna(s) [{', '.join(colunas)}]")
    return (
        "Banco carimbado no head do Alembic, mas o schema está INCOMPLETO: faltam "
        + " e ".join(faltas)
        + ". O carimbo mente (banco legado stampado sem a DDL correspondente). "
        "Faça BACKUP, rode `flask db stamp --purge <revisão real>` (no legado de "
        f"produção é {_REVISAO_LEGADO_PRE_BASELINE}) e `flask db upgrade`. "
        f"Passo a passo em {_RUNBOOK}. "
        "Emergência: SKIP_SCHEMA_CHECK=1 pula esta verificação."
    )


def verify_schema_structure() -> None:
    """Confere que o schema materializado bate com ``db.metadata``; erra alto se não.

    Requer app context. Ex. de uso: ``verify_schema_structure()`` → ``None`` num
    banco íntegro, ``SchemaVersionMismatch`` num legado sem ``etapa_responsavel``.
    """
    inspector = inspect(db.engine)
    existentes = set(inspector.get_table_names())
    tabelas = sorted(nome for nome in db.metadata.tables if nome not in existentes)
    colunas = _colunas_ausentes(inspector, existentes)
    if tabelas or colunas:
        raise SchemaVersionMismatch(_mensagem_schema_incompleto(tabelas, colunas))


def verify_schema_version() -> str | None:
    """Compara banco × head (e a estrutura) e devolve a revisão OK; divergência erra.

    Requer app context ativo. Ex. de uso (boot): ``verify_schema_version() -> 'ab12…'``.
    """
    if os.getenv("SKIP_SCHEMA_CHECK", "").strip().lower() in {"1", "true", "yes"}:
        return None

    head = alembic_head_revision()
    current = database_schema_revision()
    if current == head:
        verify_schema_structure()
        return current
    # Banco com schema materializado mas sem histórico Alembic válido é o caso
    # legado real (pré-baseline): upgrade falharia; o caminho é adotar a baseline.
    schema_materializado = inspect(db.engine).has_table("project")
    if current is None and not schema_materializado:
        raise SchemaVersionMismatch(
            "Banco vazio (sem alembic_version e sem tabelas). Instalação limpa: "
            f"rode `flask db upgrade` para criar o schema {head!r} e depois os "
            "comandos de dados do README (scripts/migrations/*.py --apply)."
        )
    if current is None or not _revisao_existe_na_cadeia(current):
        raise SchemaVersionMismatch(
            f"Banco legado pré-baseline (alembic_version={current!r} não existe na "
            f"cadeia atual, head {head!r}). Faça BACKUP do banco e rode "
            f"`flask db stamp --purge {_REVISAO_LEGADO_PRE_BASELINE}` seguido de "
            "`flask db upgrade` para adotar a baseline — carimbar `head` deixaria o "
            f"upgrade no-op e o schema incompleto. Passo a passo em {_RUNBOOK}. "
            "Emergência: SKIP_SCHEMA_CHECK=1 pula esta verificação."
        )
    raise SchemaVersionMismatch(
        f"Schema do banco está na revisão {current!r}, mas o código espera {head!r}. "
        "Rode `alembic upgrade head` (ou `flask db upgrade`) antes de subir a aplicação. "
        "Emergência: SKIP_SCHEMA_CHECK=1 pula esta verificação."
    )
