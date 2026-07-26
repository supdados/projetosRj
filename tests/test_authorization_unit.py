"""Testes unitários para services/authorization.py.

Trava do comportamento ATUAL de escopo (S1/F0-2): o ramo não-admin NÃO filtra
``ativo`` em ponto nenhum — vínculo em órgão desativado pelo sync SIORG continua
resolvendo todos os descendentes.
"""

import pytest
from sqlalchemy import event

from models import OrgaoUnidade, db
from routes import orgao_scope
from services.authorization import (
    ADMIN_RANK,
    PAPEL_EDITOR,
    PAPEL_GESTOR,
    PAPEL_LEITOR,
    PAPEL_RANK,
    effective_project_rank,
    get_user_orgao_role_map,
    get_user_orgao_subtree_ids,
    user_can_access_project,
    user_can_edit_project,
    user_can_manage_project,
    user_can_view_project,
)
from services.orgao_tree import rebuild_orgao_closure

# ── Fakes nomeados ────────────────────────────────────────────────────────────


class FakeVinculo:
    """Substitui ``UserOrgao``: o serviço só lê ``orgao_id`` e ``papel``.

    ``papel=None`` reproduz a linha legada anterior ao backfill.
    """

    def __init__(self, orgao_id: int, papel: str | None = None) -> None:
        self.orgao_id = orgao_id
        self.papel = papel


class FakeUser:
    """Substitui ``User``: o serviço só lê ``id``, ``is_admin`` e ``orgaos``."""

    def __init__(
        self,
        *,
        is_admin: bool = False,
        orgao_ids: tuple[int, ...] = (),
        vinculos: tuple[tuple[int, str], ...] = (),
        user_id: int | None = None,
    ):
        self.id = user_id
        self.is_admin = is_admin
        self.orgaos = [FakeVinculo(oid) for oid in orgao_ids]
        self.orgaos += [FakeVinculo(oid, papel) for oid, papel in vinculos]


class SqlQueryCounter:
    """Conta statements executados no engine — guarda-corpo do N+1."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.total = 0

    def _on_execute(self, *_args) -> None:
        self.total += 1

    def __enter__(self) -> "SqlQueryCounter":
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self.engine, "before_cursor_execute", self._on_execute)


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


# ── get_user_orgao_role_map ───────────────────────────────────────────────────


def test_role_map_de_vinculo_unico_propaga_rank_a_subarvore(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),))
        assert get_user_orgao_role_map(user) == {
            orgao_arvore["sec"]: PAPEL_RANK[PAPEL_EDITOR],
            orgao_arvore["sub"]: PAPEL_RANK[PAPEL_EDITOR],
            orgao_arvore["sup"]: PAPEL_RANK[PAPEL_EDITOR],
        }


def test_role_map_multi_vinculo_mantem_papeis_distintos_por_ramo(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(
            vinculos=(
                (orgao_arvore["sub"], PAPEL_EDITOR),
                (orgao_arvore["outra"], PAPEL_LEITOR),
            )
        )
        assert get_user_orgao_role_map(user) == {
            orgao_arvore["sub"]: PAPEL_RANK[PAPEL_EDITOR],
            orgao_arvore["sup"]: PAPEL_RANK[PAPEL_EDITOR],
            orgao_arvore["outra"]: PAPEL_RANK[PAPEL_LEITOR],
        }


def test_sobreposicao_pai_gestor_filho_leitor_resolve_por_max(app, orgao_arvore):
    """Sem deny: o rank maior vence na interseção (§5.1 do plano)."""
    with app.app_context():
        user = FakeUser(
            vinculos=(
                (orgao_arvore["sec"], PAPEL_GESTOR),
                (orgao_arvore["sub"], PAPEL_LEITOR),
            )
        )
        role_map = get_user_orgao_role_map(user)
        assert role_map[orgao_arvore["sub"]] == PAPEL_RANK[PAPEL_GESTOR]
        assert role_map[orgao_arvore["sup"]] == PAPEL_RANK[PAPEL_GESTOR]


def test_sobreposicao_pai_leitor_filho_gestor_eleva_so_o_ramo(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(
            vinculos=(
                (orgao_arvore["sec"], PAPEL_LEITOR),
                (orgao_arvore["sub"], PAPEL_GESTOR),
            )
        )
        assert get_user_orgao_role_map(user) == {
            orgao_arvore["sec"]: PAPEL_RANK[PAPEL_LEITOR],
            orgao_arvore["sub"]: PAPEL_RANK[PAPEL_GESTOR],
            orgao_arvore["sup"]: PAPEL_RANK[PAPEL_GESTOR],
        }


def test_role_map_de_admin_da_admin_rank_a_todos_os_ativos(app, orgao_arvore):
    with app.app_context():
        role_map = get_user_orgao_role_map(FakeUser(is_admin=True))
        assert set(role_map.values()) == {ADMIN_RANK}
        assert {orgao_arvore["sec"], orgao_arvore["outra"]} <= set(role_map)
        assert orgao_arvore["morto"] not in role_map


def test_role_map_sem_vinculo_e_vazio(app, orgao_arvore):
    with app.app_context():
        assert get_user_orgao_role_map(FakeUser()) == {}
        assert get_user_orgao_role_map(None) == {}


def test_role_map_de_orgao_inativo_alcanca_descendentes_inativos(app, orgao_arvore):
    """Trava do não-filtro de ``ativo`` no ramo não-admin (semântica da S1)."""
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["morto"], PAPEL_EDITOR),))
        assert get_user_orgao_role_map(user) == {
            orgao_arvore["morto"]: PAPEL_RANK[PAPEL_EDITOR],
            orgao_arvore["morto_filho"]: PAPEL_RANK[PAPEL_EDITOR],
        }


def test_vinculo_sem_papel_vale_gestor(app, orgao_arvore):
    """Linha legada anterior ao backfill mantém o poder que já tinha."""
    with app.app_context():
        user = FakeUser(orgao_ids=(orgao_arvore["sub"],))
        assert get_user_orgao_role_map(user) == {
            orgao_arvore["sub"]: PAPEL_RANK[PAPEL_GESTOR],
            orgao_arvore["sup"]: PAPEL_RANK[PAPEL_GESTOR],
        }


def test_role_map_usa_uma_query_de_closure_para_n_vinculos(app, orgao_arvore):
    with app.app_context():
        rebuild_orgao_closure()
        db.session.commit()
        user = FakeUser(
            vinculos=(
                (orgao_arvore["sec"], PAPEL_GESTOR),
                (orgao_arvore["morto"], PAPEL_LEITOR),
            )
        )
        with SqlQueryCounter(db.engine) as counter:
            role_map = get_user_orgao_role_map(user)
        assert counter.total == 1
        assert role_map[orgao_arvore["sup"]] == PAPEL_RANK[PAPEL_GESTOR]
        assert role_map[orgao_arvore["morto_filho"]] == PAPEL_RANK[PAPEL_LEITOR]


def test_segunda_chamada_no_mesmo_request_nao_consulta_o_banco(app, orgao_arvore):
    with app.test_request_context("/"):
        user = FakeUser(user_id=4321, vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),))
        primeiro = get_user_orgao_role_map(user)
        with SqlQueryCounter(db.engine) as counter:
            segundo = get_user_orgao_role_map(user)
        assert counter.total == 0
        assert segundo == primeiro


def test_cache_do_request_nao_vaza_entre_usuarios(app, orgao_arvore):
    with app.test_request_context("/"):
        um = FakeUser(user_id=11, vinculos=((orgao_arvore["sub"], PAPEL_LEITOR),))
        outro = FakeUser(user_id=22, vinculos=((orgao_arvore["outra"], PAPEL_GESTOR),))
        assert get_user_orgao_role_map(um) == {
            orgao_arvore["sub"]: PAPEL_RANK[PAPEL_LEITOR],
            orgao_arvore["sup"]: PAPEL_RANK[PAPEL_LEITOR],
        }
        assert get_user_orgao_role_map(outro) == {
            orgao_arvore["outra"]: PAPEL_RANK[PAPEL_GESTOR]
        }


# ── Paridade entre role map e subtree ids ─────────────────────────────────────


def test_subtree_ids_sao_as_chaves_do_role_map(app, orgao_arvore):
    with app.app_context():
        usuarios = (
            FakeUser(is_admin=True),
            FakeUser(),
            FakeUser(orgao_ids=(orgao_arvore["sec"],)),
            FakeUser(orgao_ids=(orgao_arvore["sub"], orgao_arvore["outra"])),
            FakeUser(vinculos=((orgao_arvore["morto"], PAPEL_LEITOR),)),
        )
        for user in usuarios:
            assert get_user_orgao_subtree_ids(user) == set(
                get_user_orgao_role_map(user)
            )


# ── effective_project_rank ────────────────────────────────────────────────────


def test_rank_efetivo_de_admin_e_o_teto(app, orgao_arvore):
    with app.app_context():
        admin = FakeUser(is_admin=True)
        assert effective_project_rank(admin, FakeProject(orgao_arvore["outra"])) == (
            ADMIN_RANK
        )
        assert effective_project_rank(admin, FakeProject(None)) == ADMIN_RANK


def test_rank_efetivo_herda_o_papel_do_orgao_do_projeto(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),))
        projeto = FakeProject(orgao_arvore["sup"])
        assert effective_project_rank(user, projeto) == PAPEL_RANK[PAPEL_EDITOR]


def test_rank_efetivo_e_zero_fora_da_subarvore(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        assert effective_project_rank(user, FakeProject(orgao_arvore["outra"])) == 0


def test_rank_efetivo_e_zero_para_projeto_sem_orgao(app, orgao_arvore):
    """Projeto legado sem ``orgao_id``: só admin (convite entra na fase 3)."""
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        assert effective_project_rank(user, FakeProject(None)) == 0
        assert effective_project_rank(user, None) == 0


def test_rank_efetivo_de_user_none_e_zero(app, orgao_arvore):
    with app.app_context():
        assert effective_project_rank(None, FakeProject(orgao_arvore["sec"])) == 0


# ── Predicados de limiar ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "papel, pode_ver, pode_editar, pode_gerir",
    [
        (PAPEL_LEITOR, True, False, False),
        (PAPEL_EDITOR, True, True, False),
        (PAPEL_GESTOR, True, True, True),
    ],
)
def test_limiares_dos_predicados_por_papel(
    app, orgao_arvore, papel, pode_ver, pode_editar, pode_gerir
):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], papel),))
        projeto = FakeProject(orgao_arvore["sup"])
        assert user_can_view_project(user, projeto) is pode_ver
        assert user_can_edit_project(user, projeto) is pode_editar
        assert user_can_manage_project(user, projeto) is pode_gerir


def test_admin_passa_nos_tres_limiares(app, orgao_arvore):
    with app.app_context():
        admin = FakeUser(is_admin=True)
        projeto = FakeProject(orgao_arvore["outra"])
        assert user_can_view_project(admin, projeto) is True
        assert user_can_edit_project(admin, projeto) is True
        assert user_can_manage_project(admin, projeto) is True


def test_sem_vinculo_falha_nos_tres_limiares(app, orgao_arvore):
    with app.app_context():
        user = FakeUser()
        projeto = FakeProject(orgao_arvore["sec"])
        assert user_can_view_project(user, projeto) is False
        assert user_can_edit_project(user, projeto) is False
        assert user_can_manage_project(user, projeto) is False


# ── Equivalência com o caminho antigo (portão da fase) ────────────────────────


def test_user_can_view_project_equivale_ao_acesso_de_hoje(app, orgao_arvore):
    """Com todo vínculo em ``gestor`` (backfill), o novo caminho não muda nada."""
    with app.app_context():
        usuarios = (
            FakeUser(is_admin=True),
            FakeUser(),
            FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),)),
            FakeUser(vinculos=((orgao_arvore["morto"], PAPEL_GESTOR),)),
        )
        orgao_ids = (
            orgao_arvore["sec"],
            orgao_arvore["sup"],
            orgao_arvore["outra"],
            orgao_arvore["morto_filho"],
            None,
        )
        for user in usuarios:
            for orgao_id in orgao_ids:
                projeto = FakeProject(orgao_id)
                assert user_can_view_project(user, projeto) == user_can_access_project(
                    user, projeto
                )
            assert user_can_view_project(user, None) == user_can_access_project(
                user, None
            )
