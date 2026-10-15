import builtins

from models import User, db
from scripts.admin import gerar_senha


def test_create_admin_user_script_creates_admin_with_hashed_password(
    app, monkeypatch, capsys
):
    monkeypatch.setattr(gerar_senha, "app", app)

    answers = iter(["novo_admin", "Novo Administrador", "Orgao Central"])
    passwords = iter(["senhaSegura123", "senhaSegura123"])

    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))
    monkeypatch.setattr(
        gerar_senha.getpass, "getpass", lambda _prompt="": next(passwords)
    )

    gerar_senha.create_admin_user()

    output = capsys.readouterr().out
    assert "Usuário administrador 'novo_admin' criado com sucesso!" in output

    with app.app_context():
        user = User.query.filter_by(username="novo_admin").first()
        assert user is not None
        assert user.name == "Novo Administrador"
        assert user.orgao == "Orgao Central"
        assert user.is_admin is True
        assert user.password_hash != "senhaSegura123"
        assert user.check_password("senhaSegura123") is True


def test_create_admin_user_script_aborts_when_username_already_exists(
    app, monkeypatch, capsys
):
    with app.app_context():
        existing = User(
            username="admin_existente",
            name="Admin Existente",
            orgao="Orgao Teste",
            is_admin=True,
        )
        existing.set_password("senha123")
        db.session.add(existing)
        db.session.commit()

    monkeypatch.setattr(gerar_senha, "app", app)
    monkeypatch.setattr(
        builtins,
        "input",
        lambda _prompt="": "admin_existente",
    )

    gerar_senha.create_admin_user()

    output = capsys.readouterr().out
    assert "ERRO: O usuário 'admin_existente' já existe. Abortando." in output

    with app.app_context():
        assert User.query.filter_by(username="admin_existente").count() == 1


def test_modo_nao_interativo_cria_admin_com_senha_do_ambiente(app, monkeypatch, capsys):
    monkeypatch.setattr(gerar_senha, "app", app)
    monkeypatch.setenv(gerar_senha.SENHA_ENV_VAR, "SenhaForte12")

    codigo = gerar_senha.main(["--usuario", "admin_auto", "--nome", "Admin Auto"])

    assert codigo == 0
    assert "Usuário administrador 'admin_auto' criado com sucesso!" in (
        capsys.readouterr().out
    )
    with app.app_context():
        user = User.query.filter_by(username="admin_auto").one()
        assert user.is_admin is True
        assert user.check_password("SenhaForte12") is True
        assert gerar_senha.existe_admin_ativo() is True


def test_modo_nao_interativo_exige_senha_no_ambiente(app, monkeypatch, capsys):
    monkeypatch.setattr(gerar_senha, "app", app)
    monkeypatch.delenv(gerar_senha.SENHA_ENV_VAR, raising=False)

    assert gerar_senha.main(["--usuario", "admin_auto"]) == 2
    assert gerar_senha.SENHA_ENV_VAR in capsys.readouterr().out


def test_modo_nao_interativo_recusa_senha_fraca(app, monkeypatch, capsys):
    monkeypatch.setattr(gerar_senha, "app", app)
    monkeypatch.setenv(gerar_senha.SENHA_ENV_VAR, "curta")

    assert gerar_senha.main(["--usuario", "admin_auto"]) == 1
    assert "mínimo 8 caracteres" in capsys.readouterr().out
    with app.app_context():
        assert User.query.filter_by(username="admin_auto").first() is None


def test_existe_admin_ativo_em_banco_sem_usuarios(app):
    with app.app_context():
        assert gerar_senha.existe_admin_ativo() is False
