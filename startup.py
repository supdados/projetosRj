"""Verificação de schema no boot (Sprint 5.3).

O boot NÃO roda mais migração nenhuma: DDL vem de ``alembic upgrade head``
(passo explícito de deploy) e mutações de dados viram comandos CLI em
``scripts/migrations/``. Aqui só se compara o ``alembic_version`` do banco com
o head de ``migrations/versions`` — divergência derruba o processo com
instrução acionável, em vez de N workers gunicorn aplicarem DDL sem lock.

Escape de emergência: ``SKIP_SCHEMA_CHECK=1`` pula a verificação (documentado
no README; usar só para subir uma instância enquanto se corrige o banco).
"""

import os
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from models import db

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


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


def verify_schema_version() -> str | None:
    """Compara banco × head e devolve a revisão OK; divergência = erro acionável.

    Requer app context ativo. Ex. de uso (boot): ``verify_schema_version() -> 'ab12…'``.
    """
    if os.getenv("SKIP_SCHEMA_CHECK", "").strip().lower() in {"1", "true", "yes"}:
        return None

    head = alembic_head_revision()
    current = database_schema_revision()
    if current == head:
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
            "`flask db stamp --purge head` seguido de `flask db upgrade` para "
            "adotar a baseline. Emergência: SKIP_SCHEMA_CHECK=1 pula esta verificação."
        )
    raise SchemaVersionMismatch(
        f"Schema do banco está na revisão {current!r}, mas o código espera {head!r}. "
        "Rode `alembic upgrade head` (ou `flask db upgrade`) antes de subir a aplicação. "
        "Emergência: SKIP_SCHEMA_CHECK=1 pula esta verificação."
    )
