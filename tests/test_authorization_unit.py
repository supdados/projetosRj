"""Testes unitários para services/authorization.py.

Trava do comportamento ATUAL de escopo (S1/F0-2): o ramo não-admin NÃO filtra
``ativo`` em ponto nenhum — vínculo em órgão desativado pelo sync SIORG continua
resolvendo todos os descendentes.
"""

from datetime import timedelta

import pytest
from flask import g
from sqlalchemy import event, text

from models import OrgaoUnidade, ProjectMember, db
from routes import orgao_scope
from routes.api.negotiation import api_admin_required
from routes.tasks.permissions import (
    _can_edit_task,
    _can_manage_task_restricted_actions,
    _can_view_task,
)
from services.authorization import (
    ACCESS_FORBIDDEN,
    ACCESS_NOT_FOUND,
    ACCESS_OK,
    ADMIN_RANK,
    PAPEL_EDITOR,
    PAPEL_GESTOR,
    PAPEL_LEITOR,
    PAPEL_RANK,
    area_project_rank,
    assignable_orgao_ids,
    can_assign_project_to_orgao,
    effective_project_rank,
    get_active_membership_map,
    get_user_orgao_role_map,
    get_user_orgao_subtree_ids,
    project_access_verdict,
    require_project_rank,
    user_can_access_project,
    user_can_edit_project,
    user_can_manage_project,
    user_can_reassign_project_to_orgao,
    user_can_view_project,
)
from services.orgao_tree import rebuild_orgao_closure
from time_utils import utc_now

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
    """Substitui ``Project``: o serviço só lê ``orgao_id`` e ``id`` (convites)."""

    def __init__(self, orgao_id: int | None, project_id: int | None = None) -> None:
        self.orgao_id = orgao_id
        self.id = project_id


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


# ── project_access_verdict (decisão ÚNICA 404-vs-403, S5/F4-2) ────────────────


@pytest.mark.parametrize("minimo", [PAPEL_LEITOR, PAPEL_EDITOR, PAPEL_GESTOR])
def test_verdict_de_rank_zero_e_not_found_em_qualquer_limiar(app, orgao_arvore, minimo):
    """Rank 0 nunca vira ``forbidden`` — é indistinguível de projeto inexistente."""
    with app.app_context():
        sem_vinculo = FakeUser()
        projeto = FakeProject(orgao_arvore["sec"])
        assert project_access_verdict(sem_vinculo, projeto, minimo) == ACCESS_NOT_FOUND


def test_verdict_de_projeto_none_e_not_found(app, orgao_arvore):
    with app.app_context():
        gestor = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        assert project_access_verdict(gestor, None, PAPEL_LEITOR) == ACCESS_NOT_FOUND


def test_verdict_de_projeto_inexistente_e_de_invisivel_sao_iguais(app, orgao_arvore):
    """Base do anti-enumeração (F4-2b): os dois casos produzem o MESMO veredito."""
    with app.app_context():
        sem_vinculo = FakeUser()
        invisivel = project_access_verdict(
            sem_vinculo, FakeProject(orgao_arvore["outra"]), PAPEL_LEITOR
        )
        inexistente = project_access_verdict(sem_vinculo, None, PAPEL_LEITOR)
        assert invisivel == inexistente == ACCESS_NOT_FOUND


def test_verdict_de_user_none_e_not_found(app, orgao_arvore):
    with app.app_context():
        projeto = FakeProject(orgao_arvore["sec"])
        assert project_access_verdict(None, projeto, PAPEL_LEITOR) == ACCESS_NOT_FOUND


@pytest.mark.parametrize(
    "papel, minimo",
    [
        (PAPEL_LEITOR, PAPEL_EDITOR),
        (PAPEL_LEITOR, PAPEL_GESTOR),
        (PAPEL_EDITOR, PAPEL_GESTOR),
    ],
)
def test_verdict_de_rank_insuficiente_acima_de_zero_e_forbidden(
    app, orgao_arvore, papel, minimo
):
    """Rank 10/20 abaixo do exigido: o usuário VÊ o projeto, logo 403."""
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], papel),))
        projeto = FakeProject(orgao_arvore["sup"])
        assert project_access_verdict(user, projeto, minimo) == ACCESS_FORBIDDEN


@pytest.mark.parametrize(
    "papel, minimo",
    [
        (PAPEL_LEITOR, PAPEL_LEITOR),
        (PAPEL_EDITOR, PAPEL_LEITOR),
        (PAPEL_EDITOR, PAPEL_EDITOR),
        (PAPEL_GESTOR, PAPEL_GESTOR),
    ],
)
def test_verdict_de_rank_suficiente_e_ok(app, orgao_arvore, papel, minimo):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], papel),))
        projeto = FakeProject(orgao_arvore["sup"])
        assert project_access_verdict(user, projeto, minimo) == ACCESS_OK


def test_verdict_de_admin_nunca_e_not_found_por_autorizacao(app, orgao_arvore):
    """Admin só toma ``not_found`` quando o projeto realmente não existe."""
    with app.app_context():
        admin = FakeUser(is_admin=True)
        for orgao_id in (orgao_arvore["outra"], orgao_arvore["morto_filho"], None):
            for minimo in (PAPEL_LEITOR, PAPEL_EDITOR, PAPEL_GESTOR):
                verdict = project_access_verdict(admin, FakeProject(orgao_id), minimo)
                assert verdict == ACCESS_OK
        assert project_access_verdict(admin, None, PAPEL_LEITOR) == ACCESS_NOT_FOUND


def test_verdict_com_convite_leitor_troca_not_found_por_forbidden(app, orgao_arvore):
    """Convite (F3-7) tira o usuário do rank 0: a negativa de escrita vira 403.

    O convite é gravado ANTES de qualquer leitura porque
    ``get_active_membership_map`` cacheia por usuário no ``g`` do contexto.
    """
    with app.app_context():
        projeto = FakeProject(orgao_arvore["outra"], project_id=903)
        _convida(903, 60, PAPEL_LEITOR)
        convidado = FakeUser(user_id=60)
        sem_convite = FakeUser(user_id=61)

        assert project_access_verdict(convidado, projeto, PAPEL_LEITOR) == ACCESS_OK
        assert (
            project_access_verdict(convidado, projeto, PAPEL_EDITOR) == ACCESS_FORBIDDEN
        )
        assert (
            project_access_verdict(sem_convite, projeto, PAPEL_LEITOR)
            == ACCESS_NOT_FOUND
        )


def test_verdict_rejeita_papel_fora_da_taxonomia(app, orgao_arvore):
    """A validação do limiar só é alcançada por quem já vê o projeto."""
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_LEITOR),))
        with pytest.raises(ValueError) as exc:
            project_access_verdict(user, FakeProject(orgao_arvore["sec"]), "dono")
        assert "dono" in str(exc.value)


# ── require_project_rank (gate HTTP no corpo do endpoint) ─────────────────────


def _envelope(denied):
    """Desempacota ``(Response, status)`` em ``(status, code)``."""
    response, status = denied
    return status, response.get_json()["error"]["code"]


@pytest.mark.parametrize(
    "papel, libera_leitor, libera_editor, libera_gestor",
    [
        (PAPEL_LEITOR, True, False, False),
        (PAPEL_EDITOR, True, True, False),
        (PAPEL_GESTOR, True, True, True),
    ],
)
def test_require_project_rank_nos_tres_limiares(
    app, orgao_arvore, papel, libera_leitor, libera_editor, libera_gestor
):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], papel),))
        projeto = FakeProject(orgao_arvore["sup"])
        liberados = (libera_leitor, libera_editor, libera_gestor)
        for minimo, libera in zip(
            (PAPEL_LEITOR, PAPEL_EDITOR, PAPEL_GESTOR), liberados
        ):
            denied = require_project_rank(projeto, minimo, user=user)
            assert (denied is None) is libera


def test_require_project_rank_nega_rank_zero_com_404_not_found(app, orgao_arvore):
    """Contrato S5: rank 0 sai em 404 — mesmo envelope do projeto inexistente."""
    with app.app_context():
        sem_vinculo = FakeUser()
        invisivel = require_project_rank(
            FakeProject(orgao_arvore["sec"]), PAPEL_LEITOR, user=sem_vinculo
        )
        inexistente = require_project_rank(None, PAPEL_LEITOR, user=sem_vinculo)

        assert _envelope(invisivel) == (404, "not_found")
        assert invisivel[0].get_json() == inexistente[0].get_json()


def test_require_project_rank_nega_rank_insuficiente_com_403_forbidden(
    app, orgao_arvore
):
    """403 fica só para quem já vê o projeto: leitor tentando ação de gestor."""
    with app.app_context():
        leitor = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_LEITOR),))
        denied = require_project_rank(
            FakeProject(orgao_arvore["sup"]), PAPEL_GESTOR, user=leitor
        )
        assert _envelope(denied) == (403, "forbidden")


def test_require_project_rank_ignora_message_no_404(app, orgao_arvore):
    """A mensagem do endpoint só vale no 403; o 404 não é customizável (F4-2b)."""
    with app.app_context():
        # Import local: o modulo de envelope puxa routes.api de volta.
        from routes.api.envelope import NOT_FOUND_MESSAGE

        denied = require_project_rank(
            FakeProject(orgao_arvore["sec"]),
            PAPEL_GESTOR,
            user=FakeUser(),
            message="Você não tem permissão para excluir este projeto.",
        )
        response, status = denied
        assert status == 404
        assert response.get_json()["error"]["message"] == NOT_FOUND_MESSAGE


def test_require_project_rank_usa_mensagem_do_endpoint(app, orgao_arvore):
    with app.app_context():
        denied = require_project_rank(
            FakeProject(orgao_arvore["sec"]),
            PAPEL_GESTOR,
            user=FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),)),
            message="Você não tem permissão para excluir este projeto.",
        )
        response, _status = denied
        assert (
            response.get_json()["error"]["message"]
            == "Você não tem permissão para excluir este projeto."
        )


def test_require_project_rank_sem_sessao_e_401(app, orgao_arvore):
    with app.app_context():
        denied = require_project_rank(FakeProject(orgao_arvore["sec"]), PAPEL_LEITOR)
        assert _envelope(denied) == (401, "unauthenticated")


def test_require_project_rank_cai_no_g_user_por_padrao(app, orgao_arvore):
    with app.app_context():
        g.user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        assert (
            require_project_rank(FakeProject(orgao_arvore["sup"]), PAPEL_GESTOR) is None
        )


def test_require_project_rank_libera_admin_em_qualquer_projeto(app, orgao_arvore):
    with app.app_context():
        admin = FakeUser(is_admin=True)
        for projeto in (FakeProject(orgao_arvore["outra"]), FakeProject(None)):
            assert require_project_rank(projeto, PAPEL_GESTOR, user=admin) is None


def test_require_project_rank_rejeita_papel_fora_da_taxonomia(app, orgao_arvore):
    """Usuário com rank > 0: sem isso o veredito sai em 404 antes da validação."""
    with app.app_context():
        with pytest.raises(ValueError) as exc:
            require_project_rank(
                FakeProject(orgao_arvore["sec"]),
                "dono",
                user=FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_LEITOR),)),
            )
        assert "dono" in str(exc.value)


# ── Regra dupla de reatribuição de Área Responsável (§5.4) ────────────────────


@pytest.mark.parametrize(
    "papel, permitido",
    [(PAPEL_LEITOR, False), (PAPEL_EDITOR, True), (PAPEL_GESTOR, True)],
)
def test_condicao_a_exige_editor_no_orgao_destino(app, orgao_arvore, papel, permitido):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], papel),))
        assert can_assign_project_to_orgao(user, orgao_arvore["sup"]) is permitido


def test_condicao_a_nega_orgao_fora_da_subarvore(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        assert can_assign_project_to_orgao(user, orgao_arvore["outra"]) is False


def test_condicao_a_nega_sem_usuario_ou_sem_orgao(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        assert can_assign_project_to_orgao(user, None) is False
        assert can_assign_project_to_orgao(None, orgao_arvore["sec"]) is False


def test_condicao_a_libera_admin(app, orgao_arvore):
    with app.app_context():
        assert can_assign_project_to_orgao(
            FakeUser(is_admin=True), orgao_arvore["morto"]
        )


def test_regra_dupla_exige_editor_no_projeto_alem_do_destino(app, orgao_arvore):
    """Fecha a 'captura': rank no destino não basta sem rank no projeto de origem."""
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),))
        projeto_alheio = FakeProject(orgao_arvore["outra"])
        assert can_assign_project_to_orgao(user, orgao_arvore["sec"]) is True
        assert (
            user_can_reassign_project_to_orgao(
                user, projeto_alheio, orgao_arvore["sec"]
            )
            is False
        )


def test_regra_dupla_nega_mover_para_orgao_arbitrario(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        projeto = FakeProject(orgao_arvore["sup"])
        assert (
            user_can_reassign_project_to_orgao(user, projeto, orgao_arvore["outra"])
            is False
        )


def test_regra_dupla_permite_editor_dentro_da_propria_subarvore(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),))
        projeto = FakeProject(orgao_arvore["sup"])
        assert user_can_reassign_project_to_orgao(user, projeto, orgao_arvore["sub"])


def test_regra_dupla_nega_leitor_nos_dois_lados(app, orgao_arvore):
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_LEITOR),))
        projeto = FakeProject(orgao_arvore["sup"])
        assert (
            user_can_reassign_project_to_orgao(user, projeto, orgao_arvore["sub"])
            is False
        )


def test_regra_dupla_libera_admin_e_nega_anonimo(app, orgao_arvore):
    with app.app_context():
        projeto = FakeProject(orgao_arvore["outra"])
        assert user_can_reassign_project_to_orgao(
            FakeUser(is_admin=True), projeto, orgao_arvore["sec"]
        )
        assert (
            user_can_reassign_project_to_orgao(None, projeto, orgao_arvore["sec"])
            is False
        )


def test_condicao_b_ignora_convite_por_construcao(app, orgao_arvore):
    """``area_project_rank`` nunca somará convite (S4) — trava da §5.4."""
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        assert area_project_rank(user, FakeProject(orgao_arvore["outra"])) == 0
        assert area_project_rank(user, FakeProject(orgao_arvore["sup"])) == (
            PAPEL_RANK[PAPEL_GESTOR]
        )


def test_regra_dupla_equivale_ao_fluxo_de_hoje_com_todo_vinculo_gestor(
    app, orgao_arvore
):
    """Backfill S2: gestor move dentro da própria subárvore exatamente como antes."""
    with app.app_context():
        user = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        subtree = get_user_orgao_subtree_ids(user)
        for destino in (orgao_arvore["sec"], orgao_arvore["sub"], orgao_arvore["sup"]):
            projeto = FakeProject(orgao_arvore["sup"])
            esperado = destino in subtree
            assert (
                user_can_reassign_project_to_orgao(user, projeto, destino) is esperado
            )


# ── assignable_orgao_ids / scoped_orgao_options (picker de escrita) ───────────


def test_assignable_ids_excluem_orgaos_de_vinculo_leitor(app, orgao_arvore):
    with app.app_context():
        leitor = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_LEITOR),))
        assert assignable_orgao_ids(leitor) == set()


def test_assignable_ids_cobrem_a_subarvore_do_vinculo_editor(app, orgao_arvore):
    with app.app_context():
        editor = FakeUser(vinculos=((orgao_arvore["sub"], PAPEL_EDITOR),))
        assert assignable_orgao_ids(editor) == {
            orgao_arvore["sub"],
            orgao_arvore["sup"],
        }


def test_assignable_ids_de_admin_cobrem_todos_os_ativos(app, orgao_arvore):
    with app.app_context():
        ids = assignable_orgao_ids(FakeUser(is_admin=True))
        assert orgao_arvore["outra"] in ids
        assert orgao_arvore["morto"] not in ids


def test_scoped_orgao_options_vazio_para_leitor(app, orgao_arvore):
    with app.app_context():
        leitor = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_LEITOR),))
        assert orgao_scope.scoped_orgao_options(leitor) == []


def test_scoped_orgao_options_do_editor_ficam_na_subarvore(app, orgao_arvore):
    with app.app_context():
        editor = FakeUser(vinculos=((orgao_arvore["sub"], PAPEL_EDITOR),))
        siglas = [o["sigla"] for o in orgao_scope.scoped_orgao_options(editor)]
        assert siglas == ["SUB", "SUP"]


def test_scoped_orgao_options_de_gestor_equivalem_a_subarvore_ativa(app, orgao_arvore):
    """Com todo vínculo em ``gestor``, o picker devolve o mesmo de antes do filtro."""
    with app.app_context():
        gestor = FakeUser(vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        ids = {o["id"] for o in orgao_scope.scoped_orgao_options(gestor)}
        ativos = {
            row_id
            for (row_id,) in db.session.query(OrgaoUnidade.id)
            .filter(OrgaoUnidade.ativo.is_(True))
            .all()
        }
        assert ids == get_user_orgao_subtree_ids(gestor) & ativos


# ── Matriz papel × ação × via de área (§3, F2-8) ──────────────────────────────


class FakeTarefa:
    """Substitui ``Task``: os gates só leem ``project``/``project_id``/``created_by_id``."""

    def __init__(self, project: FakeProject | None, *, autor_id: int | None) -> None:
        self.project = project
        self.project_id = None if project is None else 1
        self.created_by_id = autor_id


@pytest.mark.parametrize(
    "papel, ve, comenta, escreve_projeto, escreve_tarefa, reatribui, gere",
    [
        (PAPEL_LEITOR, True, True, False, False, False, False),
        (PAPEL_EDITOR, True, True, True, True, True, False),
        (PAPEL_GESTOR, True, True, True, True, True, True),
    ],
)
def test_matriz_papel_acao_na_via_de_area(
    app,
    orgao_arvore,
    papel,
    ve,
    comenta,
    escreve_projeto,
    escreve_tarefa,
    reatribui,
    gere,
):
    """Uma célula por linha da matriz da §3; falha se qualquer gate for removido.

    Vias cobertas pelo mesmo gate: ver alimenta lista/detalhe/dashboard/busca;
    comentar usa ``_can_view_task`` (routes/tasks/comments.py e
    ``/api/tarefas/<id>/comentarios``); escrever tarefa usa ``_can_edit_task``
    (rotas legadas, board e drawer); excluir/concluir usam
    ``user_can_manage_project``.
    """
    with app.app_context():
        user = FakeUser(user_id=10, vinculos=((orgao_arvore["sec"], papel),))
        projeto = FakeProject(orgao_arvore["sup"])
        tarefa = FakeTarefa(projeto, autor_id=99)
        assert user_can_view_project(user, projeto) is ve
        assert _can_view_task(user, tarefa) is comenta
        assert user_can_edit_project(user, projeto) is escreve_projeto
        assert _can_edit_task(user, tarefa) is escreve_tarefa
        assert (
            user_can_reassign_project_to_orgao(user, projeto, orgao_arvore["sub"])
            is reatribui
        )
        assert user_can_manage_project(user, projeto) is gere


def test_matriz_admin_passa_em_todas_as_celulas(app, orgao_arvore):
    with app.app_context():
        admin = FakeUser(is_admin=True, user_id=1)
        projeto = FakeProject(orgao_arvore["outra"])
        tarefa = FakeTarefa(projeto, autor_id=99)
        assert user_can_view_project(admin, projeto) is True
        assert _can_view_task(admin, tarefa) is True
        assert user_can_edit_project(admin, projeto) is True
        assert _can_edit_task(admin, tarefa) is True
        assert user_can_reassign_project_to_orgao(admin, projeto, orgao_arvore["sec"])
        assert user_can_manage_project(admin, projeto) is True
        assert _can_manage_task_restricted_actions(admin, tarefa) is True


@pytest.mark.parametrize("papel", [PAPEL_LEITOR, PAPEL_EDITOR, PAPEL_GESTOR])
def test_matriz_finalizar_excluir_tarefa_alheia_nega_todo_papel(
    app, orgao_arvore, papel
):
    """Célula 'finalizar/excluir alheia': admin ou autor — gestor NÃO herda (§9.1)."""
    with app.app_context():
        user = FakeUser(user_id=10, vinculos=((orgao_arvore["sec"], papel),))
        tarefa_alheia = FakeTarefa(FakeProject(orgao_arvore["sup"]), autor_id=99)
        assert _can_manage_task_restricted_actions(user, tarefa_alheia) is False


def test_matriz_autor_mantem_acoes_restritas_da_propria_tarefa(app, orgao_arvore):
    with app.app_context():
        autor = FakeUser(user_id=10, vinculos=((orgao_arvore["sec"], PAPEL_GESTOR),))
        tarefa_propria = FakeTarefa(FakeProject(orgao_arvore["sup"]), autor_id=10)
        assert _can_manage_task_restricted_actions(autor, tarefa_propria) is True


@pytest.mark.parametrize("papel", [PAPEL_LEITOR, PAPEL_EDITOR, PAPEL_GESTOR])
def test_matriz_importar_csv_e_crud_admin_negam_todo_papel(app, orgao_arvore, papel):
    """Célula 'importar CSV / CRUD admin': ``api_admin_required`` só libera admin."""

    @api_admin_required
    def acao_admin() -> str:
        return "ok"

    with app.app_context():
        g.user = FakeUser(user_id=10, vinculos=((orgao_arvore["sec"], papel),))
        response, status = acao_admin()
        assert status == 403
        assert response.get_json()["error"]["code"] == "forbidden"


def test_matriz_importar_csv_e_crud_admin_liberam_admin(app):
    @api_admin_required
    def acao_admin() -> str:
        return "ok"

    with app.app_context():
        g.user = FakeUser(is_admin=True, user_id=1)
        assert acao_admin() == "ok"


# ── Convites por projeto (S4: F3-6 rank efetivo + F3-7 wrapper de leitura) ────


def _convida(project_id: int, user_id: int, papel: str) -> ProjectMember:
    convite = ProjectMember(
        project_id=project_id, user_id=user_id, papel=papel, granted_by_id=1
    )
    db.session.add(convite)
    db.session.flush()
    return convite


def test_convite_leitor_da_leitura_sem_vinculo_de_area(app, orgao_arvore):
    with app.app_context():
        convidado = FakeUser(user_id=50)
        projeto = FakeProject(orgao_arvore["outra"], project_id=901)
        _convida(901, 50, PAPEL_LEITOR)
        assert effective_project_rank(convidado, projeto) == PAPEL_RANK[PAPEL_LEITOR]
        assert user_can_access_project(convidado, projeto) is True
        assert user_can_view_project(convidado, projeto) is True
        assert user_can_edit_project(convidado, projeto) is False


def test_convite_editor_da_edicao_mas_nunca_gestao(app, orgao_arvore):
    with app.app_context():
        convidado = FakeUser(user_id=50)
        projeto = FakeProject(orgao_arvore["outra"], project_id=901)
        _convida(901, 50, PAPEL_EDITOR)
        assert effective_project_rank(convidado, projeto) == PAPEL_RANK[PAPEL_EDITOR]
        assert user_can_edit_project(convidado, projeto) is True
        assert user_can_manage_project(convidado, projeto) is False
        assert require_project_rank(projeto, PAPEL_EDITOR, user=convidado) is None
        assert _envelope(
            require_project_rank(projeto, PAPEL_GESTOR, user=convidado)
        ) == (403, "forbidden")


def test_rank_efetivo_soma_convite_por_max_sem_subtrair(app, orgao_arvore):
    """Regra 4 da §5.2: editor da área convidado como leitor continua editor."""
    with app.app_context():
        projeto = FakeProject(orgao_arvore["sup"], project_id=902)
        editor_de_area = FakeUser(
            user_id=51, vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),)
        )
        _convida(902, 51, PAPEL_LEITOR)
        assert effective_project_rank(editor_de_area, projeto) == (
            PAPEL_RANK[PAPEL_EDITOR]
        )
        leitor_de_area = FakeUser(
            user_id=52, vinculos=((orgao_arvore["sec"], PAPEL_LEITOR),)
        )
        _convida(902, 52, PAPEL_EDITOR)
        assert effective_project_rank(leitor_de_area, projeto) == (
            PAPEL_RANK[PAPEL_EDITOR]
        )


def test_convite_alcanca_projeto_sem_orgao(app, orgao_arvore):
    """Regra 5 da §5.2: projeto legado sem ``orgao_id`` abre por admin OU convite."""
    with app.app_context():
        convidado = FakeUser(user_id=50)
        projeto_orfao = FakeProject(None, project_id=903)
        assert user_can_access_project(convidado, projeto_orfao) is False
        _convida(903, 50, PAPEL_LEITOR)
        assert effective_project_rank(convidado, projeto_orfao) == (
            PAPEL_RANK[PAPEL_LEITOR]
        )
        assert user_can_access_project(convidado, projeto_orfao) is True


def test_linha_adulterada_com_gestor_no_banco_clampa_a_editor(app, orgao_arvore):
    """Teto rígido do convite: gestor via project_member nunca vira gestão."""
    with app.app_context():
        db.session.execute(
            text(
                "INSERT INTO project_member "
                "(project_id, user_id, papel, origem, granted_by_id, created_at) "
                "VALUES (904, 50, 'gestor', 'convite', 1, :agora)"
            ),
            {"agora": utc_now()},
        )
        convidado = FakeUser(user_id=50)
        projeto = FakeProject(orgao_arvore["outra"], project_id=904)
        assert effective_project_rank(convidado, projeto) == PAPEL_RANK[PAPEL_EDITOR]
        assert user_can_manage_project(convidado, projeto) is False


def test_convite_expirado_ou_revogado_nao_conta(app, orgao_arvore):
    with app.app_context():
        projeto = FakeProject(orgao_arvore["outra"], project_id=905)
        expirado = _convida(905, 53, PAPEL_EDITOR)
        expirado.expires_at = utc_now() - timedelta(days=1)
        revogado = _convida(905, 54, PAPEL_EDITOR)
        revogado.revoked_at = utc_now()
        db.session.flush()
        assert effective_project_rank(FakeUser(user_id=53), projeto) == 0
        assert effective_project_rank(FakeUser(user_id=54), projeto) == 0
        assert user_can_access_project(FakeUser(user_id=53), projeto) is False


def test_convite_nao_afeta_area_project_rank_nem_regra_dupla(app, orgao_arvore):
    """Captura da §5.4 re-testada com convite REAL: convidado-editor não move."""
    with app.app_context():
        convidado_editor = FakeUser(
            user_id=55, vinculos=((orgao_arvore["outra"], PAPEL_EDITOR),)
        )
        projeto_convidado = FakeProject(orgao_arvore["sec"], project_id=906)
        _convida(906, 55, PAPEL_EDITOR)
        assert effective_project_rank(convidado_editor, projeto_convidado) == (
            PAPEL_RANK[PAPEL_EDITOR]
        )
        assert area_project_rank(convidado_editor, projeto_convidado) == 0
        assert can_assign_project_to_orgao(convidado_editor, orgao_arvore["outra"])
        assert (
            user_can_reassign_project_to_orgao(
                convidado_editor, projeto_convidado, orgao_arvore["outra"]
            )
            is False
        )


def test_admin_nao_precisa_de_convite_nem_e_rebaixado_por_ele(app, orgao_arvore):
    with app.app_context():
        admin = FakeUser(is_admin=True, user_id=56)
        projeto = FakeProject(orgao_arvore["outra"], project_id=907)
        assert effective_project_rank(admin, projeto) == ADMIN_RANK
        _convida(907, 56, PAPEL_LEITOR)
        assert effective_project_rank(admin, projeto) == ADMIN_RANK


def test_sem_convites_rank_efetivo_equivale_ao_de_area(app, orgao_arvore):
    """Equivalência S4: zero linhas em project_member ⇒ comportamento bit-a-bit."""
    with app.app_context():
        usuarios = (
            FakeUser(is_admin=True, user_id=60),
            FakeUser(user_id=61),
            FakeUser(user_id=62, vinculos=((orgao_arvore["sec"], PAPEL_EDITOR),)),
            FakeUser(user_id=63, vinculos=((orgao_arvore["outra"], PAPEL_GESTOR),)),
        )
        projetos = (
            FakeProject(orgao_arvore["sup"], project_id=910),
            FakeProject(orgao_arvore["outra"], project_id=911),
            FakeProject(None, project_id=912),
            None,
        )
        for user in usuarios:
            assert get_active_membership_map(user) == {}
            for projeto in projetos:
                assert effective_project_rank(user, projeto) == area_project_rank(
                    user, projeto
                )


def test_wrapper_de_acesso_inclui_convite(app, orgao_arvore):
    """F3-7: os ~35 call sites de leitura herdam o convite pelo wrapper."""
    with app.app_context():
        convidado = FakeUser(user_id=57)
        projeto = FakeProject(orgao_arvore["outra"], project_id=908)
        assert orgao_scope.user_can_access_project(convidado, projeto) is False
        _convida(908, 57, PAPEL_LEITOR)
        assert orgao_scope.user_can_access_project(convidado, projeto) is True
