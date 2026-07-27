"""Testes do relatório de grants órfãos (S4/F3-25, §7 do plano).

Órfão = convite ATIVO cujo concedente perdeu o rank gestor no projeto (via área)
ou foi soft-deletado. Relatório de housekeeping: só lê, nunca revoga nada.
"""

from datetime import timedelta

import pytest

from models import OrgaoUnidade, Project, ProjectMember, User, UserOrgao, db
from services.authorization import PAPEL_EDITOR, PAPEL_GESTOR, PAPEL_LEITOR
from services.authorization_reports import (
    MOTIVO_CONCEDENTE_REMOVIDO,
    MOTIVO_CONCEDENTE_SEM_GESTAO,
    list_orphan_grants,
)
from services.orgao_tree import rebuild_orgao_closure
from time_utils import utc_now

# ── Helpers de fixture ────────────────────────────────────────────────────────


def _add_user(username: str, *, is_admin: bool = False) -> User:
    user = User(
        username=username, name=username.upper(), password_hash="x", is_admin=is_admin
    )
    db.session.add(user)
    db.session.flush()
    return user


def _vincula(user: User, orgao_id: int, papel: str) -> None:
    db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel=papel))
    db.session.flush()


def _convida(project_id: int, user_id: int, granted_by_id: int, **campos):
    convite = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        papel=PAPEL_LEITOR,
        granted_by_id=granted_by_id,
        **campos,
    )
    db.session.add(convite)
    db.session.flush()
    return convite


@pytest.fixture
def cenario(app):
    """Um projeto em AREA, um convidado e um concedente ainda gestor."""
    with app.app_context():
        orgao = OrgaoUnidade(sigla="AREA", nome="AREA", tipo="Secretaria", ordem=0)
        db.session.add(orgao)
        db.session.flush()
        rebuild_orgao_closure()
        projeto = Project(titulo="Projeto AREA", orgao_id=orgao.id)
        db.session.add(projeto)
        db.session.flush()
        concedente = _add_user("concedente")
        _vincula(concedente, orgao.id, PAPEL_GESTOR)
        convidado = _add_user("convidado")
        db.session.commit()
        yield {
            "orgao": orgao.id,
            "projeto": projeto.id,
            "concedente": concedente.id,
            "convidado": convidado.id,
        }


# ── Sem órfãos ────────────────────────────────────────────────────────────────


def test_sem_convites_o_relatorio_e_vazio(app, cenario):
    with app.app_context():
        assert list_orphan_grants() == []


def test_concedente_ainda_gestor_nao_aparece(app, cenario):
    with app.app_context():
        _convida(cenario["projeto"], cenario["convidado"], cenario["concedente"])
        assert list_orphan_grants() == []


def test_concedente_admin_nao_aparece(app, cenario):
    with app.app_context():
        admin = _add_user("root", is_admin=True)
        _convida(cenario["projeto"], cenario["convidado"], admin.id)
        assert list_orphan_grants() == []


# ── Órfãos ────────────────────────────────────────────────────────────────────


def test_concedente_rebaixado_vira_grant_orfao(app, cenario):
    with app.app_context():
        _convida(cenario["projeto"], cenario["convidado"], cenario["concedente"])
        vinculo = UserOrgao.query.filter_by(user_id=cenario["concedente"]).one()
        vinculo.papel = PAPEL_EDITOR
        db.session.flush()
        (orfao,) = list_orphan_grants()
        assert orfao["motivo"] == MOTIVO_CONCEDENTE_SEM_GESTAO
        assert orfao["project_id"] == cenario["projeto"]
        assert orfao["granted_by_id"] == cenario["concedente"]
        assert orfao["user_id"] == cenario["convidado"]


def test_concedente_soft_deletado_vira_grant_orfao(app, cenario):
    with app.app_context():
        _convida(cenario["projeto"], cenario["convidado"], cenario["concedente"])
        db.session.get(User, cenario["concedente"]).deleted_at = utc_now()
        db.session.flush()
        (orfao,) = list_orphan_grants()
        assert orfao["motivo"] == MOTIVO_CONCEDENTE_REMOVIDO


def test_concedente_que_perdeu_o_vinculo_vira_grant_orfao(app, cenario):
    with app.app_context():
        _convida(cenario["projeto"], cenario["convidado"], cenario["concedente"])
        UserOrgao.query.filter_by(user_id=cenario["concedente"]).delete()
        db.session.flush()
        (orfao,) = list_orphan_grants()
        assert orfao["motivo"] == MOTIVO_CONCEDENTE_SEM_GESTAO


def test_gestao_do_concedente_nunca_vem_de_convite(app, cenario):
    """Convite não sustenta convite: quem só tem convite conta como órfão."""
    with app.app_context():
        so_convidado = _add_user("so_convite")
        _convida(cenario["projeto"], so_convidado.id, cenario["concedente"])
        outro = _add_user("outro")
        _convida(cenario["projeto"], outro.id, so_convidado.id)
        motivos = {orfao["motivo"] for orfao in list_orphan_grants()}
        assert motivos == {MOTIVO_CONCEDENTE_SEM_GESTAO}


# ── Convite inativo sai do relatório ──────────────────────────────────────────


def test_convite_revogado_nao_aparece_mesmo_com_concedente_removido(app, cenario):
    with app.app_context():
        convite = _convida(
            cenario["projeto"], cenario["convidado"], cenario["concedente"]
        )
        convite.revoked_at = utc_now()
        db.session.get(User, cenario["concedente"]).deleted_at = utc_now()
        db.session.flush()
        assert list_orphan_grants() == []


def test_convite_expirado_nao_aparece(app, cenario):
    with app.app_context():
        _convida(
            cenario["projeto"],
            cenario["convidado"],
            cenario["concedente"],
            expires_at=utc_now() - timedelta(days=1),
        )
        db.session.get(User, cenario["concedente"]).deleted_at = utc_now()
        db.session.flush()
        assert list_orphan_grants() == []


def test_relatorio_nao_muda_o_banco(app, cenario):
    with app.app_context():
        _convida(cenario["projeto"], cenario["convidado"], cenario["concedente"])
        db.session.get(User, cenario["concedente"]).deleted_at = utc_now()
        db.session.commit()
        list_orphan_grants()
        convite = ProjectMember.query.one()
        assert convite.revoked_at is None
        assert convite.is_active is True
