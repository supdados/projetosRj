import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

from scripts.migrations import migrate_production


def _load_migration_unificacao_module():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "migrations"
        / "migration_unificacao_tarefas"
    )
    loader = SourceFileLoader("migration_unificacao_tarefas", str(script_path))
    spec = importlib.util.spec_from_loader("migration_unificacao_tarefas", loader)
    if spec is None or spec.loader is None:
        raise AssertionError(
            "Não foi possível carregar migration_unificacao_tarefas para teste."
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migrate_production_build_engine_prefers_database_url(monkeypatch):
    captured = {}

    monkeypatch.setenv(
        "DATABASE_URL", "mysql+pymysql://user:secret@db.example.com/projetos"
    )
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.setattr(
        migrate_production,
        "create_engine",
        lambda uri: captured.setdefault("engine", SimpleNamespace(uri=uri)),
    )

    engine = migrate_production.build_engine()

    assert engine.uri == "mysql+pymysql://user:secret@db.example.com/projetos"


def test_migrate_production_build_engine_builds_uri_from_env(monkeypatch):
    captured = {}

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_USER", "db_user")
    monkeypatch.setenv("DB_PASSWORD", "senha com espaco")
    monkeypatch.setenv("DB_NAME", "projetos")
    monkeypatch.setenv("DB_HOST", "mysql.internal")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setattr(
        migrate_production,
        "create_engine",
        lambda uri: captured.setdefault("engine", SimpleNamespace(uri=uri)),
    )

    engine = migrate_production.build_engine()

    assert (
        engine.uri
        == "mysql+pymysql://db_user:senha+com+espaco@mysql.internal:3307/projetos"
    )


def test_migration_unificacao_build_engine_requires_env_or_database_url(monkeypatch):
    migration_unificacao = _load_migration_unificacao_module()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    try:
        migration_unificacao.build_engine()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Era esperado SystemExit(1) sem variáveis de conexão.")
