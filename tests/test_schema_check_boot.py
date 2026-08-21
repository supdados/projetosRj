"""Sprint 5.3: o boot só VERIFICA o schema (alembic_version × head) e falha alto."""

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app import create_app
from models import db
from startup import (
    _REVISAO_LEGADO_PRE_BASELINE,
    SchemaVersionMismatch,
    alembic_head_revision,
    database_schema_revision,
    verify_schema_version,
)


def _stamp(revision: str) -> None:
    db.session.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32))")
    )
    db.session.execute(text("DELETE FROM alembic_version"))
    db.session.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
        {"rev": revision},
    )
    db.session.commit()


def test_head_revision_resolve_do_script_directory(app):
    with app.app_context():
        head = alembic_head_revision()
    assert isinstance(head, str) and len(head) == 12


def test_banco_populado_sem_alembic_version_manda_stampar(app):
    # O conftest cria o schema via create_all: é o retrato do banco legado
    # pré-baseline (tabelas materializadas, histórico Alembic ausente).
    with app.app_context():
        assert database_schema_revision() is None
        with pytest.raises(SchemaVersionMismatch) as excinfo:
            verify_schema_version()
    mensagem = str(excinfo.value)
    assert f"flask db stamp --purge {_REVISAO_LEGADO_PRE_BASELINE}" in mensagem
    # Carimbar o head deixaria o `upgrade` seguinte no-op: o banco legado ficaria
    # sem a DDL da baseline e do catch-up, com o carimbo mentindo para sempre.
    assert "stamp --purge head" not in mensagem
    assert "docs/runbook-migracao-producao-v5.md" in mensagem


def test_revisao_pre_baseline_existe_na_cadeia(app):
    from startup import _revisao_existe_na_cadeia

    with app.app_context():
        assert _revisao_existe_na_cadeia(_REVISAO_LEGADO_PRE_BASELINE)
        assert _REVISAO_LEGADO_PRE_BASELINE != alembic_head_revision()


def test_banco_stampado_no_head_passa(app):
    with app.app_context():
        head = alembic_head_revision()
        _stamp(head)
        assert verify_schema_version() == head


def test_stamp_orfao_manda_adotar_baseline(app):
    # Revisão que não existe na cadeia (caso real: produção em 7c1d9e4a2b3f,
    # apagada do git) — `flask db upgrade` falharia; o caminho é stamp + upgrade.
    with app.app_context():
        _stamp("deadbeef0000")
        with pytest.raises(SchemaVersionMismatch) as excinfo:
            verify_schema_version()
    mensagem = str(excinfo.value)
    assert "deadbeef0000" in mensagem
    assert alembic_head_revision() in mensagem
    assert f"flask db stamp --purge {_REVISAO_LEGADO_PRE_BASELINE}" in mensagem
    assert "stamp --purge head" not in mensagem


def test_banco_atras_do_head_manda_rodar_upgrade(app):
    # Revisão VÁLIDA da cadeia, só atrasada: upgrade normal resolve.
    from startup import _alembic_script_directory

    base = _alembic_script_directory().get_base()
    with app.app_context():
        _stamp(base)
        with pytest.raises(SchemaVersionMismatch) as excinfo:
            verify_schema_version()
    mensagem = str(excinfo.value)
    assert base in mensagem
    assert "alembic upgrade head" in mensagem
    assert "stamp" not in mensagem


def test_skip_schema_check_e_escape_de_emergencia(app, monkeypatch):
    monkeypatch.setenv("SKIP_SCHEMA_CHECK", "1")
    with app.app_context():
        assert verify_schema_version() is None


def test_create_app_em_testing_nao_roda_verificacao(tmp_path):
    # Sem alembic_version no banco: se a verificação rodasse, o boot quebraria.
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'boot.sqlite'}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
        }
    )
    assert flask_app.config["TESTING"] is True


def test_create_app_sem_testing_falha_alto_em_banco_nao_migrado(tmp_path):
    with pytest.raises(SchemaVersionMismatch, match="flask db upgrade"):
        create_app(
            {
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'raw.sqlite'}",
                "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
                "SKIP_STARTUP_DB_INIT": False,
            }
        )


def test_flask_db_cli_nao_dispara_verificacao(tmp_path, monkeypatch):
    # `flask db upgrade` importa o app: sem esta exceção seria impossível
    # migrar um banco divergente (a verificação abortaria antes do upgrade).
    monkeypatch.setattr(
        "sys.argv", ["/fake/.venv/bin/flask", "db", "upgrade"], raising=False
    )
    flask_app = create_app(
        {
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'cli.sqlite'}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": False,
        }
    )
    assert flask_app.config["TESTING"] is False


def test_python_m_flask_db_tambem_e_detectado(tmp_path, monkeypatch):
    # `python -m flask db stamp head` tem argv[0]=".../python": a detecção é
    # por `db <subcomando>`, não pelo nome do binário.
    monkeypatch.setattr(
        "sys.argv",
        [
            "/fake/.venv/bin/python",
            "-m",
            "flask",
            "--app",
            "app",
            "db",
            "stamp",
            "head",
        ],
        raising=False,
    )
    create_app(
        {
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'cli2.sqlite'}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": False,
        }
    )


def _drop(sql: str) -> None:
    db.session.execute(text(sql))
    db.session.commit()


def test_head_carimbado_com_tabela_faltando_falha(app):
    # Caso real de produção: banco legado stampado no head, sem a DDL da baseline.
    with app.app_context():
        _stamp(alembic_head_revision())
        _drop("DROP TABLE etapa_responsavel")
        with pytest.raises(SchemaVersionMismatch) as excinfo:
            verify_schema_version()
    mensagem = str(excinfo.value)
    assert "etapa_responsavel" in mensagem
    assert "INCOMPLETO" in mensagem
    assert "1 tabela(s)" in mensagem


def test_head_carimbado_com_coluna_critica_faltando_falha(app):
    with app.app_context():
        _stamp(alembic_head_revision())
        _drop("ALTER TABLE orgao_unidade DROP COLUMN data_fim_vigencia")
        with pytest.raises(SchemaVersionMismatch) as excinfo:
            verify_schema_version()
    mensagem = str(excinfo.value)
    assert "orgao_unidade.data_fim_vigencia" in mensagem
    assert "stamp --purge head" not in mensagem


def test_skip_schema_check_pula_tambem_a_estrutural(app, monkeypatch):
    monkeypatch.setenv("SKIP_SCHEMA_CHECK", "1")
    with app.app_context():
        _stamp(alembic_head_revision())
        _drop("DROP TABLE etapa_responsavel")
        assert verify_schema_version() is None


def test_verify_schema_structure_passa_em_banco_integro(app):
    from startup import verify_schema_structure

    with app.app_context():
        assert verify_schema_structure() is None
