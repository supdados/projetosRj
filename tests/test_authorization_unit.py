"""Testes unitários para services/authorization.py.

Trava do comportamento ATUAL de escopo (S1/F0-2): o ramo não-admin NÃO filtra
``ativo`` em ponto nenhum — vínculo em órgão desativado pelo sync SIORG continua
resolvendo todos os descendentes.
"""

import pytest

from models import OrgaoUnidade, db
from routes import orgao_scope
from services.authorization import (
    ADMIN_RANK,
    PAPEL_EDITOR,
    PAPEL_GESTOR,
    PAPEL_LEITOR,
    PAPEL_RANK,
    get_user_orgao_subtree_ids,
    user_can_access_project,
)

# ── Fakes nomeados ────────────────────────────────────────────────────────────


class FakeVinculo:
    """Substitui ``UserOrgao``: o serviço só lê ``orgao_id``."""

    def __init__(self, orgao_id: int) -> None:
        self.orgao_id = orgao_id


class FakeUser:
    """Substitui ``User``: o serviço só lê ``is_admin`` e ``orgaos``."""

    def __init__(self, *, is_admin: bool = False, orgao_ids: tuple[int, ...] = ()):
        self.is_admin = is_admin
        self.orgaos = [FakeVinculo(oid) for oid in orgao_ids]


class FakeProject:
    """Substitui ``Project``: o serviço só lê ``orgao_id``."""

    def __init__(self, orgao_id: int | None) -> None:
        self.orgao_id = orgao_id


# ── Fixture de árvore ─────────────────────────────────────────────────────────


def _add_orgao(sigla: str, pai_id: int | None, tipo: str, ativo: bool = True) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo=tipo, pai_id=pai_id, ordem=0, ativo=ativo
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


@pytest.fixture
def orgao_arvore(app):
    """SEC → SUB → SUP, mais um ramo irmão OUTRA e um órgão inativo MORTO."""
    with app.app_context():
        sec = _add_orgao("SEC", None, "Secretaria")
        sub = _add_orgao("SUB", sec, "Subsecretaria")
        sup = _add_orgao("SUP", sub, "Superintendência")
        outra = _add_orgao("OUTRA", None, "Secretaria")
        morto = _add_orgao("MORTO", None, "Secretaria", ativo=False)
        morto_filho = _add_orgao("MORTOFILHO", morto, "Subsecretaria", ativo=False)
        db.session.commit()
        yield {
            "sec": sec,
            "sub": sub,
            "sup": sup,
            "outra": outra,
            "morto": morto,
            "morto_filho": morto_filho,
        }


# ── Constantes de papel ───────────────────────────────────────────────────────


def test_papel_rank_ordena_leitor_editor_gestor():
    assert PAPEL_RANK[PAPEL_LEITOR] < PAPEL_RANK[PAPEL_EDITOR]
    assert PAPEL_RANK[PAPEL_EDITOR] < PAPEL_RANK[PAPEL_GESTOR]


def test_admin_rank_e_teto_acima_de_gestor():
    assert ADMIN_RANK > PAPEL_RANK[PAPEL_GESTOR]


# ── get_user_orgao_subtree_ids ────────────────────────────────────────────────


def test_admin_ve_todos_os_orgaos_ativos(app, orgao_arvore):
    with app.app_context():
        ids = get_user_orgao_subtree_ids(FakeUser(is_admin=True))
        assert {orgao_arvore["sec"], orgao_arvore["sub"], orgao_arvore["sup"]} <= ids
        assert orgao_arvore["outra"] in ids
        assert orgao_arvore["morto"] not in ids
        assert orgao_arvore["morto_filho"] not in ids


def test_vinculo_unico_inclui_raiz_e_descendentes(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sec"],))
        ids = get_user_orgao_subtree_ids(user)
        assert ids == {orgao_arvore["sec"], orgao_arvore["sub"], orgao_arvore["sup"]}


def test_multi_vinculo_une_as_duas_subarvores(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sub"], orgao_arvore["outra"]))
        ids = get_user_orgao_subtree_ids(user)
        assert ids == {orgao_arvore["sub"], orgao_arvore["sup"], orgao_arvore["outra"]}
        assert orgao_arvore["sec"] not in ids


def test_sobreposicao_pai_e_filho_nao_perde_nem_duplica(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sec"], orgao_arvore["sub"]))
        ids = get_user_orgao_subtree_ids(user)
        assert ids == {orgao_arvore["sec"], orgao_arvore["sub"], orgao_arvore["sup"]}


def test_sem_vinculo_retorna_conjunto_vazio(app, orgao_arvore):
    with app.app_context():
        assert get_user_orgao_subtree_ids(FakeUser()) == set()


def test_user_none_retorna_conjunto_vazio(app, orgao_arvore):
    with app.app_context():
        assert get_user_orgao_subtree_ids(None) == set()


def test_vinculo_em_orgao_inativo_resolve_descendentes_inativos(app, orgao_arvore):
    """Trava do não-filtro de ``ativo`` no ramo não-admin (§5.1 do plano)."""
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["morto"],))
        ids = get_user_orgao_subtree_ids(user)
        assert ids == {orgao_arvore["morto"], orgao_arvore["morto_filho"]}


# ── user_can_access_project ───────────────────────────────────────────────────


def test_admin_acessa_qualquer_projeto(app, orgao_arvore):
    with app.app_context():
        admin = FakeUser(is_admin=True)
        assert (
            user_can_access_project(admin, FakeProject(orgao_arvore["outra"])) is True
        )
        assert user_can_access_project(admin, FakeProject(None)) is True


def test_projeto_na_subarvore_e_acessivel(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sec"],))
        assert user_can_access_project(user, FakeProject(orgao_arvore["sup"])) is True


def test_projeto_fora_da_subarvore_nao_e_acessivel(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sec"],))
        assert (
            user_can_access_project(user, FakeProject(orgao_arvore["outra"])) is False
        )


def test_projeto_sem_orgao_nao_e_acessivel_a_nao_admin(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sec"],))
        assert user_can_access_project(user, FakeProject(None)) is False


def test_projeto_none_nao_e_acessivel(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sec"],))
        assert user_can_access_project(user, None) is False


def test_user_none_nao_acessa_projeto(app, orgao_arvore):
    with app.app_context():
        assert user_can_access_project(None, FakeProject(orgao_arvore["sec"])) is False


# ── Paridade com os wrappers de routes/orgao_scope.py ─────────────────────────


def test_wrapper_de_subtree_devolve_o_mesmo_que_o_servico(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sub"], orgao_arvore["outra"]))
        assert orgao_scope.get_user_orgao_subtree_ids(
            user
        ) == get_user_orgao_subtree_ids(user)


def test_wrapper_de_acesso_devolve_o_mesmo_que_o_servico(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sec"],))
        for orgao_id in (orgao_arvore["sup"], orgao_arvore["outra"], None):
            projeto = FakeProject(orgao_id)
            assert orgao_scope.user_can_access_project(
                user, projeto
            ) == user_can_access_project(user, projeto)
