"""Testes de services/project_membership.py (S4/F3-10 e F3-13).

Cobre as flags que a SPA recebe prontas (`permissions`/`access_via`), o teto de
gestão do convite, a feature flag `CONVITES_HABILITADOS` e a lista read-only de
membros herdados por área (UMA query).
"""

from datetime import timedelta

import pytest

from models import OrgaoUnidade, Project, ProjectMember, User, UserOrgao, db
from services.authorization import (
    PAPEL_EDITOR,
    PAPEL_GESTOR,
    PAPEL_LEITOR,
    user_can_edit_project,
)
from services.orgao_tree import rebuild_orgao_closure
from services.project_membership import (
    ACCESS_VIA_ADMIN,
    ACCESS_VIA_AMBOS,
    ACCESS_VIA_AREA,
    ACCESS_VIA_CONVITE,
    convites_habilitados,
    list_inherited_members,
    project_access_via,
    project_permission_flags,
    user_can_manage_members,
)
from tests.sql_query_counter import SqlQueryCounter
from time_utils import utc_now

# ── Fakes nomeados ────────────────────────────────────────────────────────────


class FakeVinculoArea:
    """Substitui ``UserOrgao``: o serviço só lê ``orgao_id`` e ``papel``."""

    def __init__(self, orgao_id: int, papel: str) -> None:
        self.orgao_id = orgao_id
        self.papel = papel


class FakeViewer:
    """Substitui ``User``: lê ``id``, ``is_admin``, ``deleted_at`` e ``orgaos``."""

    def __init__(
        self,
        user_id: int | None = None,
        *,
        vinculos: tuple[tuple[int, str], ...] = (),
        is_admin: bool = False,
    ) -> None:
        self.id = user_id
        self.is_admin = is_admin
        self.deleted_at = None
        self.orgaos = [FakeVinculoArea(oid, papel) for oid, papel in vinculos]


class FakeProjeto:
    """Substitui ``Project``: o serviço só lê ``id`` e ``orgao_id``."""

    def __init__(self, project_id: int | None, orgao_id: int | None) -> None:
        self.id = project_id
        self.orgao_id = orgao_id


# ── Helpers de fixture ────────────────────────────────────────────────────────


def _add_orgao(sigla: str, pai_id: int | None) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=pai_id, ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(username: str, *, deleted: bool = False) -> User:
    user = User(
        username=username,
        name=username.upper(),
        password_hash="x",
        deleted_at=utc_now() if deleted else None,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _vincula(user: User, orgao_id: int, papel: str) -> None:
    db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel=papel))
    db.session.flush()


def _convida(project_id: int, user_id: int, papel: str, *, revogado: bool = False):
    convite = ProjectMember(
        project_id=project_id, user_id=user_id, papel=papel, granted_by_id=1
    )
    if revogado:
        convite.revoked_at = utc_now()
    db.session.add(convite)
    db.session.flush()
    return convite


@pytest.fixture
def arvore(app):
    """SEC → SUB (o projeto vive em SUB) e um ramo irmão OUTRA."""
    with app.app_context():
        sec = _add_orgao("SEC", None)
        sub = _add_orgao("SUB", sec)
        neto = _add_orgao("NETO", sub)
        outra = _add_orgao("OUTRA", None)
        rebuild_orgao_closure()
        projeto = Project(titulo="Projeto SUB", orgao_id=sub)
        db.session.add(projeto)
        # Commit (não flush): cada teste roda no próprio contexto/sessão.
        db.session.commit()
        yield {
            "sec": sec,
            "sub": sub,
            "neto": neto,
            "outra": outra,
            "projeto_id": projeto.id,
            "projeto": FakeProjeto(projeto.id, sub),
        }


# ── access_via ────────────────────────────────────────────────────────────────


def test_access_via_admin_vence_tudo(app, arvore):
    with app.test_request_context("/"):
        admin = FakeViewer(1, is_admin=True)
        assert project_access_via(admin, arvore["projeto"]) == ACCESS_VIA_ADMIN


def test_access_via_area_para_vinculado(app, arvore):
    with app.test_request_context("/"):
        user = FakeViewer(2, vinculos=((arvore["sec"], PAPEL_LEITOR),))
        assert project_access_via(user, arvore["projeto"]) == ACCESS_VIA_AREA


def test_access_via_convite_para_quem_so_tem_convite(app, arvore):
    with app.test_request_context("/"):
        _convida(arvore["projeto_id"], 3, PAPEL_EDITOR)
        assert (
            project_access_via(FakeViewer(3), arvore["projeto"]) == ACCESS_VIA_CONVITE
        )


def test_access_via_ambos_quando_ha_area_e_convite(app, arvore):
    """A SPA trata `ambos` como convidado (badge) sem perder a via de área."""
    with app.test_request_context("/"):
        _convida(arvore["projeto_id"], 4, PAPEL_EDITOR)
        user = FakeViewer(4, vinculos=((arvore["sub"], PAPEL_LEITOR),))
        assert project_access_via(user, arvore["projeto"]) == ACCESS_VIA_AMBOS


def test_access_via_admin_vence_ate_o_convite(app, arvore):
    with app.test_request_context("/"):
        _convida(arvore["projeto_id"], 15, PAPEL_EDITOR)
        admin = FakeViewer(15, is_admin=True)
        assert project_access_via(admin, arvore["projeto"]) == ACCESS_VIA_ADMIN


def test_access_via_none_sem_area_e_sem_convite(app, arvore):
    with app.test_request_context("/"):
        user = FakeViewer(5, vinculos=((arvore["outra"], PAPEL_GESTOR),))
        assert project_access_via(user, arvore["projeto"]) is None


def test_access_via_convite_revogado_nao_conta(app, arvore):
    with app.test_request_context("/"):
        _convida(arvore["projeto_id"], 6, PAPEL_EDITOR, revogado=True)
        assert project_access_via(FakeViewer(6), arvore["projeto"]) is None


# ── permissions ───────────────────────────────────────────────────────────────


def test_flags_do_gestor_de_area_com_flag_ligada(app, arvore):
    with app.test_request_context("/"):
        app.config["CONVITES_HABILITADOS"] = True
        gestor = FakeViewer(7, vinculos=((arvore["sub"], PAPEL_GESTOR),))
        assert project_permission_flags(gestor, arvore["projeto"]) == {
            "can_edit": True,
            "can_manage": True,
            "can_manage_members": True,
        }


def test_flags_do_editor_de_area_nao_gerenciam(app, arvore):
    with app.test_request_context("/"):
        app.config["CONVITES_HABILITADOS"] = True
        editor = FakeViewer(8, vinculos=((arvore["sub"], PAPEL_EDITOR),))
        assert project_permission_flags(editor, arvore["projeto"]) == {
            "can_edit": True,
            "can_manage": False,
            "can_manage_members": False,
        }


def test_convite_editor_edita_mas_nunca_gerencia_membros(app, arvore):
    """Teto do convite (Redmine #11075): gestão de membros só via área/admin."""
    with app.test_request_context("/"):
        app.config["CONVITES_HABILITADOS"] = True
        _convida(arvore["projeto_id"], 9, PAPEL_EDITOR)
        flags = project_permission_flags(FakeViewer(9), arvore["projeto"])
        assert flags == {
            "can_edit": True,
            "can_manage": False,
            "can_manage_members": False,
        }


def test_flag_desligada_esconde_gestao_de_membros_do_gestor(app, arvore):
    with app.test_request_context("/"):
        app.config["CONVITES_HABILITADOS"] = False
        gestor = FakeViewer(10, vinculos=((arvore["sub"], PAPEL_GESTOR),))
        assert convites_habilitados() is False
        assert user_can_manage_members(gestor, arvore["projeto"]) is False
        assert project_permission_flags(gestor, arvore["projeto"])["can_manage"] is True


def test_flag_desligada_esconde_gestao_de_membros_do_admin(app, arvore):
    with app.test_request_context("/"):
        app.config["CONVITES_HABILITADOS"] = False
        admin = FakeViewer(11, is_admin=True)
        assert user_can_manage_members(admin, arvore["projeto"]) is False
        app.config["CONVITES_HABILITADOS"] = True
        assert user_can_manage_members(admin, arvore["projeto"]) is True


def test_sem_viewer_todas_as_flags_sao_falsas(app, arvore):
    with app.test_request_context("/"):
        assert project_permission_flags(None, arvore["projeto"]) == {
            "can_edit": False,
            "can_manage": False,
            "can_manage_members": False,
        }
        assert project_access_via(None, arvore["projeto"]) is None


def test_sem_convites_flags_equivalem_ao_comportamento_atual(app, arvore):
    """Equivalência S4: sem linha em project_member nada muda para o usuário."""
    with app.test_request_context("/"):
        assert ProjectMember.query.count() == 0
        user = FakeViewer(12, vinculos=((arvore["sec"], PAPEL_EDITOR),))
        flags = project_permission_flags(user, arvore["projeto"])
        assert flags["can_edit"] is user_can_edit_project(user, arvore["projeto"])


def test_flags_de_n_projetos_custam_as_mesmas_duas_queries(app, arvore):
    """Zero N+1: os dois mapas são cacheados em `g`, o resto é lookup em dict."""
    with app.test_request_context("/"):
        user = FakeViewer(13, vinculos=((arvore["sec"], PAPEL_EDITOR),))
        projetos = [FakeProjeto(numero, arvore["sub"]) for numero in range(1, 51)]
        with SqlQueryCounter(db.engine) as counter:
            flags = [project_permission_flags(user, projeto) for projeto in projetos]
        assert counter.total == 2
        assert all(item["can_edit"] for item in flags)


# ── list_inherited_members ────────────────────────────────────────────────────


def test_membros_herdados_incluem_proprio_orgao_e_ancestrais(app, arvore):
    with app.app_context():
        ana = _add_user("ana")
        bruno = _add_user("bruno")
        _vincula(ana, arvore["sub"], PAPEL_EDITOR)
        _vincula(bruno, arvore["sec"], PAPEL_GESTOR)
        membros = list_inherited_members(arvore["projeto"])
        assert [(m["username"], m["papel"], m["via_orgao_sigla"]) for m in membros] == [
            ("ana", PAPEL_EDITOR, "SUB"),
            ("bruno", PAPEL_GESTOR, "SEC"),
        ]


def test_membros_herdados_ignoram_vinculo_em_descendente_ou_ramo_irmao(app, arvore):
    with app.app_context():
        _vincula(_add_user("neto"), arvore["neto"], PAPEL_GESTOR)
        _vincula(_add_user("alheio"), arvore["outra"], PAPEL_GESTOR)
        assert list_inherited_members(arvore["projeto"]) == []


def test_membros_herdados_excluem_usuario_soft_deletado(app, arvore):
    with app.app_context():
        removido = _add_user("removido", deleted=True)
        _vincula(removido, arvore["sub"], PAPEL_GESTOR)
        assert list_inherited_members(arvore["projeto"]) == []


def test_membro_vinculado_a_dois_ancestrais_aparece_uma_vez_com_maior_papel(
    app, arvore
):
    with app.app_context():
        duplo = _add_user("duplo")
        _vincula(duplo, arvore["sub"], PAPEL_LEITOR)
        _vincula(duplo, arvore["sec"], PAPEL_GESTOR)
        membros = list_inherited_members(arvore["projeto"])
        assert len(membros) == 1
        assert membros[0]["papel"] == PAPEL_GESTOR


def test_membros_herdados_usam_uma_query(app, arvore):
    with app.app_context():
        for numero in range(10):
            _vincula(_add_user(f"user{numero}"), arvore["sec"], PAPEL_LEITOR)
        with SqlQueryCounter(db.engine) as counter:
            membros = list_inherited_members(arvore["projeto"])
        assert counter.total == 1
        assert len(membros) == 10


def test_projeto_sem_orgao_nao_tem_membro_herdado_nem_query(app, arvore):
    with app.app_context():
        with SqlQueryCounter(db.engine) as counter:
            assert list_inherited_members(FakeProjeto(999, None)) == []
        assert counter.total == 0


def test_listar_herdados_nao_cria_linha_de_convite(app, arvore):
    """Herdado é read-only: nunca vira linha em project_member (§6.5)."""
    with app.app_context():
        _vincula(_add_user("carla"), arvore["sec"], PAPEL_GESTOR)
        assert list_inherited_members(arvore["projeto"])
        assert ProjectMember.query.count() == 0


def test_convite_nao_aparece_entre_os_herdados(app, arvore):
    """Convidado não é membro de área: não pode vazar para a lista herdada."""
    with app.app_context():
        convidado = _add_user("convidado")
        _convida(arvore["projeto_id"], convidado.id, PAPEL_EDITOR)
        assert list_inherited_members(arvore["projeto"]) == []


def test_convite_expirado_some_da_via_de_acesso(app, arvore):
    with app.test_request_context("/"):
        convite = _convida(arvore["projeto_id"], 14, PAPEL_EDITOR)
        convite.expires_at = utc_now() - timedelta(days=1)
        db.session.flush()
        assert project_access_via(FakeViewer(14), arvore["projeto"]) is None
