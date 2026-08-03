"""Política pura de concessão de `is_admin` (services/admin_grant_policy.py).

Só o administrador PRINCIPAL (``is_super_admin``, eleito por migração) pode
conceder ou remover a flag `is_admin`, editar/excluir contas de administrador e
a própria conta dele nunca pode ser despromovida nem excluída. Estes testes
exercitam a política sem HTTP: instâncias reais de ``User`` com ``flush()`` (os
ids importam para a regra de auto-edição), nenhum commit, nenhum request.
"""

from __future__ import annotations

from models import User, db
from services.admin_grant_policy import (
    MSG_ATOR_AUSENTE,
    MSG_CONCEDER_NEGADO,
    MSG_GERIR_ADMIN_NEGADO,
    MSG_REMOVER_NEGADO,
    MSG_SUPER_ADMIN_IMUTAVEL,
    MSG_SUPER_ADMIN_INDELEVEL,
    apply_admin_flag,
    can_grant_admin,
    denial_for_admin_flag_change,
    denial_for_deleting_user,
    denial_for_managing_user,
    is_super_admin,
    resolve_admin_flag,
)
from time_utils import utc_now


def _novo(
    username: str,
    *,
    is_admin: bool = False,
    super_admin: bool = False,
    removido: bool = False,
) -> User:
    """Cria e faz flush de um usuário mínimo (id preenchido, sem commit)."""
    user = User(
        username=username,
        name=username.replace("_", " ").title(),
        password_hash="x",
        is_admin=is_admin,
        is_super_admin=super_admin,
    )
    if removido:
        user.deleted_at = utc_now()
    db.session.add(user)
    db.session.flush()
    return user


# ── is_super_admin ────────────────────────────────────────────────────────────


def test_is_super_admin_para_none_e_false(app):
    with app.app_context():
        assert is_super_admin(None) is False


def test_is_super_admin_false_quando_flag_desligada(app):
    with app.app_context():
        assert is_super_admin(_novo("comum", is_admin=True)) is False


def test_is_super_admin_true_quando_flag_ligada(app):
    with app.app_context():
        assert is_super_admin(_novo("chefe", is_admin=True, super_admin=True)) is True


def test_is_super_admin_false_quando_soft_deletado(app):
    """Fail-closed: super admin removido não exerce mais o poder de concessão."""
    with app.app_context():
        removido = _novo("chefe_off", is_admin=True, super_admin=True, removido=True)
        assert is_super_admin(removido) is False


# ── can_grant_admin ───────────────────────────────────────────────────────────


def test_can_grant_admin_so_para_super_admin(app):
    with app.app_context():
        assert can_grant_admin(_novo("chefe", is_admin=True, super_admin=True)) is True
        assert can_grant_admin(_novo("adm", is_admin=True)) is False
        assert can_grant_admin(_novo("ze")) is False
        assert can_grant_admin(None) is False


# ── denial_for_admin_flag_change ──────────────────────────────────────────────


def test_super_admin_pode_conceder_e_remover(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        comum = _novo("ze")
        outro_admin = _novo("adm", is_admin=True)

        assert denial_for_admin_flag_change(chefe, comum, True) is None
        assert denial_for_admin_flag_change(chefe, outro_admin, False) is None


def test_admin_comum_nao_concede_nem_remove(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        comum = _novo("ze")
        outro_admin = _novo("adm2", is_admin=True)

        conceder = denial_for_admin_flag_change(ator, comum, True)
        remover = denial_for_admin_flag_change(ator, outro_admin, False)

        assert conceder == MSG_CONCEDER_NEGADO.format(alvo=comum.username)
        assert remover == MSG_REMOVER_NEGADO.format(alvo=outro_admin.username)
        assert "administrador principal" in conceder
        assert "administrador principal" in remover


def test_super_admin_nunca_perde_a_flag_nem_por_si_mesmo(app):
    """Regra (d): a conta principal não pode ser despromovida por ninguém."""
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        outro_admin = _novo("adm", is_admin=True)
        esperado = MSG_SUPER_ADMIN_IMUTAVEL.format(alvo=chefe.username)

        assert denial_for_admin_flag_change(chefe, chefe, False) == esperado
        assert denial_for_admin_flag_change(outro_admin, chefe, False) == esperado


def test_no_op_nunca_e_negado(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        ator = _novo("adm", is_admin=True)
        ja_admin = _novo("adm2", is_admin=True)
        comum = _novo("ze")

        assert denial_for_admin_flag_change(chefe, ja_admin, True) is None
        assert denial_for_admin_flag_change(ator, ja_admin, True) is None
        assert denial_for_admin_flag_change(ator, comum, False) is None


def test_criacao_sem_alvo_respeita_o_ator(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        ator = _novo("adm", is_admin=True)

        assert denial_for_admin_flag_change(chefe, None, True) is None
        assert denial_for_admin_flag_change(ator, None, False) is None
        assert denial_for_admin_flag_change(ator, None, True) == (
            MSG_CONCEDER_NEGADO.format(alvo="novo usuário")
        )


def test_sem_ator_a_mudanca_real_e_negada(app):
    with app.app_context():
        comum = _novo("ze")
        assert denial_for_admin_flag_change(None, comum, True) == MSG_ATOR_AUSENTE


# ── denial_for_managing_user ──────────────────────────────────────────────────


def test_super_admin_gerencia_qualquer_alvo(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        assert denial_for_managing_user(chefe, _novo("ze")) is None
        assert denial_for_managing_user(chefe, _novo("adm", is_admin=True)) is None
        assert denial_for_managing_user(chefe, chefe) is None


def test_admin_comum_gerencia_apenas_nao_admins(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        comum = _novo("ze")
        outro_admin = _novo("adm2", is_admin=True)
        chefe = _novo("chefe", is_admin=True, super_admin=True)

        assert denial_for_managing_user(ator, comum) is None
        assert denial_for_managing_user(ator, outro_admin) == (
            MSG_GERIR_ADMIN_NEGADO.format(alvo=outro_admin.username)
        )
        assert denial_for_managing_user(ator, chefe) == (
            MSG_GERIR_ADMIN_NEGADO.format(alvo=chefe.username)
        )


def test_admin_comum_pode_gerenciar_a_si_mesmo(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        assert denial_for_managing_user(ator, ator) is None


def test_gerir_sem_ator_ou_sem_alvo_e_negado(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        assert denial_for_managing_user(None, ator) == MSG_ATOR_AUSENTE
        assert denial_for_managing_user(ator, None) == MSG_ATOR_AUSENTE


# ── denial_for_deleting_user ──────────────────────────────────────────────────


def test_super_admin_e_indelevel_inclusive_por_si_mesmo(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        ator = _novo("adm", is_admin=True)
        esperado = MSG_SUPER_ADMIN_INDELEVEL.format(alvo=chefe.username)

        assert denial_for_deleting_user(chefe, chefe) == esperado
        assert denial_for_deleting_user(ator, chefe) == esperado


def test_exclusao_delega_a_regra_de_gestao(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        ator = _novo("adm", is_admin=True)
        outro_admin = _novo("adm2", is_admin=True)
        comum = _novo("ze")

        assert denial_for_deleting_user(ator, outro_admin) == (
            MSG_GERIR_ADMIN_NEGADO.format(alvo=outro_admin.username)
        )
        assert denial_for_deleting_user(chefe, outro_admin) is None
        assert denial_for_deleting_user(ator, comum) is None


# ── resolve_admin_flag ────────────────────────────────────────────────────────


def test_resolve_flag_ausente_mantem_valor_atual(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        alvo = _novo("adm2", is_admin=True)

        assert resolve_admin_flag(ator, alvo, None) == (True, None)


def test_resolve_flag_igual_ao_atual_nao_nega(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        comum = _novo("ze")

        assert resolve_admin_flag(ator, comum, False) == (False, None)


def test_resolve_flag_diferente_sem_poder_devolve_atual_e_mensagem(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        comum = _novo("ze")

        efetivo, denial = resolve_admin_flag(ator, comum, True)

        assert efetivo is False
        assert denial == MSG_CONCEDER_NEGADO.format(alvo=comum.username)


def test_resolve_flag_super_admin_promove(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        comum = _novo("ze")

        assert resolve_admin_flag(chefe, comum, True) == (True, None)


# ── apply_admin_flag ──────────────────────────────────────────────────────────


def test_apply_muta_quando_permitido(app):
    with app.app_context():
        chefe = _novo("chefe", is_admin=True, super_admin=True)
        comum = _novo("ze")

        assert apply_admin_flag(chefe, comum, True) is None
        assert comum.is_admin is True


def test_apply_nao_muta_quando_negado(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        comum = _novo("ze")

        denial = apply_admin_flag(ator, comum, True)

        assert denial == MSG_CONCEDER_NEGADO.format(alvo=comum.username)
        assert comum.is_admin is False


def test_apply_com_requested_none_preserva_o_valor(app):
    with app.app_context():
        ator = _novo("adm", is_admin=True)
        alvo = _novo("adm2", is_admin=True)

        assert apply_admin_flag(ator, alvo, None) is None
        assert alvo.is_admin is True
