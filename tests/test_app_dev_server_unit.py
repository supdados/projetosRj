"""`python app.py` (só dev) e a pasta do SQLite criada no boot."""

from __future__ import annotations

from app import dev_server_options, ensure_sqlite_dir


def test_dev_server_default_so_localhost(monkeypatch):
    monkeypatch.delenv("APP_HOST", raising=False)
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.setenv("FLASK_DEBUG", "1")

    assert dev_server_options() == {
        "host": "127.0.0.1",
        "port": 5002,
        "debug": True,
    }


def test_dev_server_le_host_e_porta_do_env(monkeypatch):
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "8000")
    monkeypatch.setenv("FLASK_DEBUG", "false")

    assert dev_server_options() == {"host": "0.0.0.0", "port": 8000, "debug": False}


def test_dev_server_porta_invalida_cai_no_padrao(monkeypatch):
    monkeypatch.setenv("APP_PORT", "abc")

    assert dev_server_options()["port"] == 5002


def test_ensure_sqlite_dir_cria_pasta_do_arquivo(tmp_path):
    pasta = tmp_path / "instance" / "sub"

    ensure_sqlite_dir(f"sqlite:///{pasta / 'app.db'}")

    assert pasta.is_dir()


def test_ensure_sqlite_dir_ignora_memoria_e_mysql(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ensure_sqlite_dir("sqlite://")
    ensure_sqlite_dir("sqlite:///:memory:")
    ensure_sqlite_dir("mysql+pymysql://u:p@localhost/db")

    assert list(tmp_path.iterdir()) == []
