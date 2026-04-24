from types import SimpleNamespace

from scripts.catalog import sync_objectives_catalog


def test_masked_db_uri_hides_password_but_preserves_user_host_and_db():
    masked = sync_objectives_catalog._masked_db_uri(
        "mysql+pymysql://usuario:segredo@db.example.com/base"
    )

    assert masked == "mysql+pymysql://usuario:***@db.example.com/base"


def test_sync_objectives_catalog_main_supports_dry_run(app, monkeypatch, capsys):
    monkeypatch.setattr(sync_objectives_catalog, "app", app)
    monkeypatch.setattr(
        sync_objectives_catalog,
        "parse_args",
        lambda: SimpleNamespace(dry_run=True, skip_create_all=False),
    )

    calls = {"create_all": 0, "commit_flag": None}

    def fake_create_all():
        calls["create_all"] += 1

    def fake_sync_goal_catalog_to_db(*, commit):
        calls["commit_flag"] = commit
        return {
            "objetivos_upserted": 3,
            "resultados_upserted": 7,
            "indicadores_upserted": 11,
        }

    monkeypatch.setattr(sync_objectives_catalog.db, "create_all", fake_create_all)
    monkeypatch.setattr(
        sync_objectives_catalog, "sync_goal_catalog_to_db", fake_sync_goal_catalog_to_db
    )

    result = sync_objectives_catalog.main()

    output = capsys.readouterr().out
    assert result == 0
    assert calls["create_all"] == 1
    assert calls["commit_flag"] is False
    assert "Modo dry-run: SIM" in output
    assert "dry-run: rollback executado" in output
    assert "- objetivos_upserted: 3" in output


def test_sync_objectives_catalog_main_returns_error_code_on_failure(
    app, monkeypatch, capsys
):
    monkeypatch.setattr(sync_objectives_catalog, "app", app)
    monkeypatch.setattr(
        sync_objectives_catalog,
        "parse_args",
        lambda: SimpleNamespace(dry_run=False, skip_create_all=True),
    )
    monkeypatch.setattr(
        sync_objectives_catalog,
        "sync_goal_catalog_to_db",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("falha controlada")),
    )

    result = sync_objectives_catalog.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "ERRO: falha controlada" in output
