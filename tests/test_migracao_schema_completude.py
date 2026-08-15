"""Sprint 5.1/5.5: a cadeia de migrações sozinha reproduz o schema dos modelos.

Guardião da cadeia Alembic: roda `upgrade head` num SQLite vazio (nenhum
`create_all` envolvido) e compara o resultado com `db.metadata`. Qualquer
migração esquecida depois de mexer nos modelos reprova aqui — e no job
`migracao` do CI, que executa exatamente este arquivo.
"""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade
from sqlalchemy import Engine, inspect
from sqlalchemy.pool import NullPool

from app import create_app
from models import db
from startup import alembic_head_revision

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture(scope="module")
def engine_migrado(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    """Engine de um SQLite vazio levado ao head só por `alembic upgrade head`."""
    db_path = tmp_path_factory.mktemp("migracao") / "head.sqlite"
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": True,
        }
    )
    with flask_app.app_context():
        # directory absoluto: o teste não pode depender do cwd do pytest.
        upgrade(directory=str(_MIGRATIONS_DIR))
        yield db.engine
        db.session.remove()
        db.engine.dispose()


def test_upgrade_head_cria_todas_as_tabelas_dos_modelos(engine_migrado: Engine) -> None:
    tabelas_no_banco = set(inspect(engine_migrado).get_table_names())
    faltando = sorted(set(db.metadata.tables) - tabelas_no_banco)
    assert not faltando, f"tabelas dos modelos ausentes após upgrade head: {faltando}"


def test_upgrade_head_cria_todas_as_colunas_dos_modelos(
    engine_migrado: Engine,
) -> None:
    inspector = inspect(engine_migrado)
    faltando: list[str] = []
    for nome_tabela, tabela in db.metadata.tables.items():
        no_banco = {coluna["name"] for coluna in inspector.get_columns(nome_tabela)}
        faltando += [
            f"{nome_tabela}.{coluna.name}"
            for coluna in tabela.columns
            if coluna.name not in no_banco
        ]
    assert not faltando, f"colunas dos modelos ausentes após upgrade head: {faltando}"


def test_autogenerate_nao_detecta_diferenca_entre_cadeia_e_modelos(
    engine_migrado: Engine,
) -> None:
    """Equivalente in-process ao `alembic check` que o CI roda contra o MySQL."""
    with engine_migrado.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), db.metadata)
    assert not diferencas, (
        "cadeia de migrações divergiu dos modelos; gere a revisão faltante com "
        f"`flask db migrate`. Diff do autogenerate: {diferencas}"
    )


def test_banco_migrado_fica_no_head_da_cadeia(engine_migrado: Engine) -> None:
    with engine_migrado.connect() as conexao:
        revisao = MigrationContext.configure(conexao).get_current_revision()
    assert revisao == alembic_head_revision()
