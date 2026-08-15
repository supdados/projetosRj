"""Sprint 5.3: eleição do super admin inicial como CLI (fora do boot)."""

from time_utils import utc_now

from models import User, db
from scripts.migrations.elect_super_admin import (
    elect_initial_super_admin,
    find_initial_super_admin_id,
)


def _criar_usuario(
    username: str, *, is_admin=False, is_super_admin=False, deleted=False
):
    user = User(
        username=username,
        name=username,
        orgao="Orgao Teste",
        is_admin=is_admin,
        is_super_admin=is_super_admin,
    )
    user.set_password("senha123")
    if deleted:
        user.deleted_at = utc_now()
    db.session.add(user)
    db.session.flush()
    return user


def test_sem_admin_ativo_nao_ha_candidato(app):
    with app.app_context():
        _criar_usuario("comum")
        _criar_usuario("admin_deletado", is_admin=True, deleted=True)
        assert find_initial_super_admin_id() is None
        assert elect_initial_super_admin() is None


def test_elege_menor_id_entre_admins_ativos(app):
    with app.app_context():
        _criar_usuario("comum")
        _criar_usuario("admin_deletado", is_admin=True, deleted=True)
        alvo = _criar_usuario("admin_a", is_admin=True)
        _criar_usuario("admin_b", is_admin=True)

        assert find_initial_super_admin_id() == alvo.id
        assert elect_initial_super_admin() == alvo.id
        db.session.commit()
        assert db.session.get(User, alvo.id).is_super_admin is True


def test_reexecucao_nunca_reelege(app):
    with app.app_context():
        alvo = _criar_usuario("admin_a", is_admin=True)
        assert elect_initial_super_admin() == alvo.id
        db.session.commit()
        _criar_usuario("admin_b", is_admin=True)
        assert elect_initial_super_admin() is None


def test_super_admin_soft_deletado_ainda_bloqueia_eleicao(app):
    with app.app_context():
        _criar_usuario("super_antigo", is_admin=True, is_super_admin=True, deleted=True)
        _criar_usuario("admin_ativo", is_admin=True)
        assert find_initial_super_admin_id() is None
        assert elect_initial_super_admin() is None


def test_dry_run_nao_muta_banco(app):
    with app.app_context():
        alvo = _criar_usuario("admin_a", is_admin=True)
        db.session.commit()
        assert find_initial_super_admin_id() == alvo.id
        assert db.session.get(User, alvo.id).is_super_admin is False
