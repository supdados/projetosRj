"""Portão de equivalência da S2 (F1-7): novo caminho == caminho antigo.

Com todo vínculo em ``gestor`` (default do backfill), o role map / rank efetivo
introduzidos na S2 têm de devolver EXATAMENTE os acessos de hoje — nada a mais,
nada a menos, inclusive editar, excluir e concluir. O oráculo é ``EscopoLegado``,
cópia literal do corpo de ``routes/orgao_scope.py`` anterior à S1 (commit
``b1baed0^``); o teste falha se um acesso for criado ou removido.

Integração leve de propósito: as fixtures são as reais do ``conftest``
(``seed_data`` + usuários/órgãos/projetos gravados no banco), não fakes — fakes
já cobrem os limiares em ``tests/test_authorization_unit.py``.
"""

import pytest

from models import OrgaoUnidade, Project, User, UserOrgao, db
from routes.orgao_tree import get_orgao_descendants
from services.authorization import (
    PAPEL_GESTOR,
    PAPEL_RANK,
    get_user_orgao_role_map,
    get_user_orgao_subtree_ids,
    user_can_access_project,
    user_can_edit_project,
    user_can_manage_project,
    user_can_view_project,
)
from services.orgao_tree import rebuild_orgao_closure

# ── Oráculo: implementação ANTIGA, preservada literalmente ────────────────────


class EscopoLegado:
    """Caminho pré-S2 de escopo/acesso, usado só como referência nos asserts."""

    @staticmethod
    def subtree_ids(user) -> set[int]:
        if user is None:
            return set()
        if getattr(user, "is_admin", False):
            rows = (
                db.session.query(OrgaoUnidade.id)
                .filter(OrgaoUnidade.ativo.is_(True))
                .all()
            )
            return {row_id for (row_id,) in rows}
        subtree: set[int] = set()
        for uo in getattr(user, "orgaos", None) or []:
            subtree.add(uo.orgao_id)
            subtree.update(get_orgao_descendants(uo.orgao_id))
        return subtree

    @staticmethod
    def pode_acessar_projeto(user, project) -> bool:
        if user is None:
            return False
        if getattr(user, "is_admin", False):
            return True
        if project is None or project.orgao_id is None:
            return False
        return project.orgao_id in EscopoLegado.subtree_ids(user)


# ── Cenário real (fixtures do conftest + complementos gravados no banco) ──────

PERFIS = (
    "admin",
    "vinculado",
    "heranca_raiz",
    "multi_vinculo",
    "sem_vinculo",
    "orgao_inativo",
)

# Único perfil cujo escopo é legitimamente vazio — os demais precisam de escopo
# não vazio para o assert de igualdade não passar por vacuidade.
PERFIS_SEM_ESCOPO = {"sem_vinculo"}


def _criar_usuario(username: str, orgao_ids: tuple[int, ...] = ()) -> User:
    """Usuário real com vínculos no papel default do backfill (``gestor``)."""
    user = User(username=username, name=username, is_admin=False)
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    for orgao_id in orgao_ids:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id))
    db.session.flush()
    return user


def _criar_orgao(sigla: str, pai_id: int | None, ativo: bool) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=pai_id, ordem=0, ativo=ativo
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _criar_projeto(titulo: str, orgao_id: int | None) -> int:
    projeto = Project(
        titulo=titulo,
        orgao_id=orgao_id,
        orgao="Orgao Equivalencia",
        prioridade="media",
        status="Vigente",
        observacao="Projeto de equivalencia",
    )
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


@pytest.fixture
def cenario(app, seed_data):
    """Completa o seed com herança, multi-vínculo, sem vínculo e ramo inativo."""
    with app.app_context():
        setd_id = OrgaoUnidade.query.filter_by(sigla="SETD").first().id
        morto_id = _criar_orgao("MORTO", None, ativo=False)
        morto_filho_id = _criar_orgao("MORTOFILHO", morto_id, ativo=False)
        auditoria_id = seed_data["auditoria_orgao_id"]
        perfis = {
            "admin": seed_data["admin_id"],
            "vinculado": seed_data["user_id"],
            "heranca_raiz": _criar_usuario("equiv_setd", (setd_id,)).id,
            "multi_vinculo": _criar_usuario(
                "equiv_multi", (auditoria_id, seed_data["vpd_orgao_id"])
            ).id,
            "sem_vinculo": _criar_usuario("equiv_sem_vinculo").id,
            "orgao_inativo": _criar_usuario("equiv_inativo", (morto_id,)).id,
        }
        projetos = {
            "auditoria": seed_data["project_id"],
            "auditoria_concluivel": seed_data["project_complete_id"],
            "vpd": seed_data["foreign_project_id"],
            "sem_orgao": _criar_projeto("Projeto Sem Orgao", None),
            "ramo_inativo": _criar_projeto("Projeto Ramo Inativo", morto_filho_id),
        }
        db.session.commit()

    # Fora do contexto (como `seed_data`): só ids, para o teste abrir o seu.
    return {
        "perfis": perfis,
        "projetos": projetos,
        "outsider_id": seed_data["outsider_id"],
        "setd_id": setd_id,
        "auditoria_id": auditoria_id,
        "vpd_id": seed_data["vpd_orgao_id"],
        "morto_id": morto_id,
        "morto_filho_id": morto_filho_id,
    }


def _usuario(cenario, perfil: str) -> User:
    return db.session.get(User, cenario["perfis"][perfil])


def _projetos(cenario) -> list[Project]:
    return [db.session.get(Project, pid) for pid in cenario["projetos"].values()]


# ── Pré-condição do portão: o backfill é gestor ───────────────────────────────


def test_todo_vinculo_do_cenario_nasce_gestor(app, cenario):
    """Sem isso, a equivalência abaixo mediria outro backfill que não o real."""
    with app.app_context():
        assert {uo.papel for uo in UserOrgao.query.all()} == {PAPEL_GESTOR}


@pytest.mark.parametrize("perfil", [p for p in PERFIS if p != "admin"])
def test_role_map_de_nao_admin_so_tem_rank_de_gestor(app, cenario, perfil):
    with app.app_context():
        role_map = get_user_orgao_role_map(_usuario(cenario, perfil))
        assert set(role_map.values()) <= {PAPEL_RANK[PAPEL_GESTOR]}


# ── Conjunto visível: novo == antigo ──────────────────────────────────────────


@pytest.mark.parametrize("perfil", PERFIS)
def test_conjunto_visivel_novo_igual_ao_antigo(app, cenario, perfil):
    with app.app_context():
        user = _usuario(cenario, perfil)
        antigo = EscopoLegado.subtree_ids(user)
        assert get_user_orgao_subtree_ids(user) == antigo
        assert (antigo == set()) is (perfil in PERFIS_SEM_ESCOPO)


@pytest.mark.parametrize("perfil", PERFIS)
def test_chaves_do_role_map_sao_o_conjunto_antigo(app, cenario, perfil):
    with app.app_context():
        user = _usuario(cenario, perfil)
        assert set(get_user_orgao_role_map(user)) == EscopoLegado.subtree_ids(user)


@pytest.mark.parametrize("perfil", PERFIS)
def test_equivalencia_se_mantem_com_a_closure_reconstruida(app, cenario, perfil):
    """A closure só é populada pelo sync SIORG: os dois caminhos valem sem e com."""
    with app.app_context():
        antes = get_user_orgao_subtree_ids(_usuario(cenario, perfil))
        rebuild_orgao_closure()
        db.session.commit()
        user = _usuario(cenario, perfil)
        assert get_user_orgao_subtree_ids(user) == EscopoLegado.subtree_ids(user)
        assert get_user_orgao_subtree_ids(user) == antes


def test_heranca_raiz_ve_toda_a_subarvore_de_setd(app, cenario):
    """Guarda contra igualdade por vacuidade: a herança descendente segue viva."""
    with app.app_context():
        ids = get_user_orgao_subtree_ids(_usuario(cenario, "heranca_raiz"))
        assert {cenario["setd_id"], cenario["auditoria_id"], cenario["vpd_id"]} <= ids
        assert cenario["morto_id"] not in ids


def test_vinculo_em_orgao_inativo_ve_descendentes_inativos(app, cenario):
    """Semântica travada: o ramo não-admin não filtra ``ativo`` (nem antes nem agora)."""
    with app.app_context():
        user = _usuario(cenario, "orgao_inativo")
        esperado = {cenario["morto_id"], cenario["morto_filho_id"]}
        assert get_user_orgao_subtree_ids(user) == esperado
        assert EscopoLegado.subtree_ids(user) == esperado


# ── user_can_access_project: idêntico antes/depois ────────────────────────────


@pytest.mark.parametrize("perfil", PERFIS)
def test_user_can_access_project_identico_ao_antigo(app, cenario, perfil):
    with app.app_context():
        user = _usuario(cenario, perfil)
        for projeto in [*_projetos(cenario), None]:
            assert user_can_access_project(user, projeto) == (
                EscopoLegado.pode_acessar_projeto(user, projeto)
            )


@pytest.mark.parametrize("perfil", PERFIS)
def test_conjunto_de_projetos_acessiveis_novo_igual_ao_antigo(app, cenario, perfil):
    with app.app_context():
        user = _usuario(cenario, perfil)
        todos = Project.query.all()
        novo = {p.id for p in todos if user_can_access_project(user, p)}
        antigo = {p.id for p in todos if EscopoLegado.pode_acessar_projeto(user, p)}
        assert novo == antigo


@pytest.mark.parametrize("perfil", PERFIS)
def test_predicados_de_rank_nao_criam_nem_removem_acesso(app, cenario, perfil):
    """Backfill gestor ⇒ ver, editar e gerir (excluir/concluir) == acesso de hoje."""
    with app.app_context():
        user = _usuario(cenario, perfil)
        for projeto in [*_projetos(cenario), None]:
            antigo = EscopoLegado.pode_acessar_projeto(user, projeto)
            assert user_can_view_project(user, projeto) is antigo
            assert user_can_edit_project(user, projeto) is antigo
            assert user_can_manage_project(user, projeto) is antigo


# ── Integração leve: as rotas continuam devolvendo o mesmo escopo ─────────────


def _ids_da_lista(client) -> set[int]:
    payload = client.get("/api/projetos?status=").get_json()
    assert payload["ok"] is True
    assert payload["data"]["pagination"]["total_pages"] <= 1
    return {card["id"] for card in payload["data"]["projetos"]}


def _permitidos_pelo_caminho_antigo(app, user_id: int) -> set[int]:
    with app.app_context():
        user = db.session.get(User, user_id)
        return {
            p.id
            for p in Project.query.all()
            if EscopoLegado.pode_acessar_projeto(user, p)
        }


def test_api_projetos_lista_so_o_escopo_do_caminho_antigo(app, cenario, client_user):
    ids = _ids_da_lista(client_user)
    permitidos = _permitidos_pelo_caminho_antigo(app, cenario["perfis"]["vinculado"])
    assert ids <= permitidos
    assert cenario["projetos"]["auditoria"] in ids
    assert cenario["projetos"]["vpd"] not in ids


def test_api_projetos_do_outsider_lista_so_o_escopo_do_caminho_antigo(
    app, cenario, client_outsider
):
    ids = _ids_da_lista(client_outsider)
    permitidos = _permitidos_pelo_caminho_antigo(app, cenario["outsider_id"])
    assert ids <= permitidos
    assert cenario["projetos"]["vpd"] in ids
    assert cenario["projetos"]["auditoria"] not in ids


@pytest.mark.parametrize("perfil", ["vinculado", "admin"])
def test_detalhe_de_projeto_responde_conforme_o_caminho_antigo(
    app, cenario, client_user, client_admin, perfil
):
    clients = {"vinculado": client_user, "admin": client_admin}
    # Só os projetos do seed: os sintéticos existem para o escopo, não para o
    # serializer de detalhe.
    alvos = ("auditoria", "auditoria_concluivel", "vpd")
    with app.app_context():
        user = _usuario(cenario, perfil)
        esperado = {
            cenario["projetos"][chave]: EscopoLegado.pode_acessar_projeto(
                user, db.session.get(Project, cenario["projetos"][chave])
            )
            for chave in alvos
        }
    for project_id, permitido in esperado.items():
        response = clients[perfil].get(f"/api/projetos/{project_id}/detalhe")
        assert (response.status_code == 200) is permitido
        # S5/F4-2: a negativa de acesso virou 404 anti-enumeração.
        assert response.status_code in (200, 404)
