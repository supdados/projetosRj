"""Regressão da extração de apply_projects_list_filters: cada filtro isolado e
combinado devolve os MESMOS ids que o bloco original de build_projects_list_context."""

import datetime

import pytest

from catalogs.abep import ABEP_INDICADORES_OPTIONS
from models import (
    Etapa,
    OrgaoUnidade,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    User,
    UserOrgao,
    db,
)
from routes.projects.list_filters import (
    ProjectsListFilters,
    apply_projects_list_filters,
)
from services.atraso import hoje_utc

ABEP_VALIDO = ABEP_INDICADORES_OPTIONS[0]["value"]


def _novo_orgao(sigla: str, pai_id: int | None) -> OrgaoUnidade:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=pai_id, ordem=0
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _novo_usuario(
    username: str, *, is_admin: bool = False, orgao_id: int | None = None
) -> User:
    usuario = User(username=username, name=username, is_admin=is_admin)
    usuario.set_password("senha123")
    db.session.add(usuario)
    db.session.flush()
    if orgao_id is not None:
        db.session.add(UserOrgao(user_id=usuario.id, orgao_id=orgao_id))
    return usuario


def _nova_etapa(project_id: int, data_fim: datetime.date) -> None:
    db.session.add(
        Etapa(
            descricao="Etapa filtro",
            data_fim=data_fim,
            done=False,
            iniciada=False,
            project_id=project_id,
            ordem=0,
            entry_type="manual",
        )
    )


def _nova_colecao(
    owner_user_id: int, nome: str, project_ids: list[int]
) -> ProjectCollection:
    colecao = ProjectCollection(owner_user_id=owner_user_id, nome=nome)
    db.session.add(colecao)
    db.session.flush()
    for ordem, project_id in enumerate(project_ids):
        db.session.add(
            ProjectCollectionItem(
                collection_id=colecao.id, project_id=project_id, ordem=ordem
            )
        )
    return colecao


@pytest.fixture
def dados(app) -> dict[str, int]:
    with app.app_context():
        raiz = _novo_orgao("LFRAIZ", None)
        filho = _novo_orgao("LFFILHO", raiz.id)
        fora = _novo_orgao("LFFORA", None)

        admin = _novo_usuario("admin_lf", is_admin=True)
        comum = _novo_usuario("comum_lf", orgao_id=raiz.id)

        alfa = Project(
            titulo="Projeto Alfa",
            orgao_id=raiz.id,
            status="Vigente",
            prioridade="Alta",
            special_project="ABEP",
            delivery_type="Sistema",
            abep_indicator=ABEP_VALIDO,
            objetivo_id=1,
        )
        beta = Project(titulo="Projeto Beta", orgao_id=filho.id, status="Vigente")
        externo = Project(titulo="Projeto Externo", orgao_id=fora.id, status="Vigente")
        suspenso = Project(
            titulo="Projeto Suspenso", orgao_id=raiz.id, status="Suspenso"
        )
        db.session.add_all([alfa, beta, externo, suspenso])
        db.session.flush()

        _nova_etapa(alfa.id, hoje_utc() - datetime.timedelta(days=2))
        _nova_etapa(beta.id, hoje_utc() + datetime.timedelta(days=2))

        minha_colecao = _nova_colecao(comum.id, "Minha", [beta.id])
        colecao_alheia = _nova_colecao(admin.id, "Alheia", [alfa.id])
        db.session.commit()
        return {
            "admin_id": admin.id,
            "comum_id": comum.id,
            "raiz_id": raiz.id,
            "alfa_id": alfa.id,
            "beta_id": beta.id,
            "externo_id": externo.id,
            "suspenso_id": suspenso.id,
            "minha_colecao_id": minha_colecao.id,
            "colecao_alheia_id": colecao_alheia.id,
        }


def _ids(user: User, **kwargs) -> set[int]:
    filters = ProjectsListFilters(**kwargs)
    query = apply_projects_list_filters(Project.query, filters, user)
    return {projeto.id for projeto in query.all()}


def test_admin_sem_filtros_ve_tudo(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin) == {
            dados["alfa_id"],
            dados["beta_id"],
            dados["externo_id"],
            dados["suspenso_id"],
        }


def test_nao_admin_restrito_a_subarvore(app, dados):
    with app.app_context():
        comum = db.session.get(User, dados["comum_id"])
        assert _ids(comum) == {
            dados["alfa_id"],
            dados["beta_id"],
            dados["suspenso_id"],
        }


def test_filtro_orgao_expande_subarvore(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, selected_orgao_id=dados["raiz_id"]) == {
            dados["alfa_id"],
            dados["beta_id"],
            dados["suspenso_id"],
        }


def test_filtro_status(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, selected_status="Suspenso") == {dados["suspenso_id"]}
        assert _ids(admin, selected_status="Vigente") == {
            dados["alfa_id"],
            dados["beta_id"],
            dados["externo_id"],
        }


def test_filtro_prioridade(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, selected_priority="Alta") == {dados["alfa_id"]}


def test_filtro_atraso(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, selected_atraso="atrasado") == {dados["alfa_id"]}
        assert _ids(admin, selected_atraso="no_prazo") == {
            dados["beta_id"],
            dados["externo_id"],
        }
        assert _ids(admin, selected_atraso="desconhecido") == set()


def test_filtro_special_e_delivery(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, selected_special_project="ABEP") == {dados["alfa_id"]}
        assert _ids(admin, selected_delivery_type="Sistema") == {dados["alfa_id"]}


def test_filtro_abep_normaliza_e_filtra(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, selected_abep_indicator=ABEP_VALIDO) == {dados["alfa_id"]}

        filters = ProjectsListFilters(selected_abep_indicator="valor invalido")
        query = apply_projects_list_filters(Project.query, filters, admin)
        assert filters.selected_abep_indicator is None
        assert {p.id for p in query.all()} == _ids(admin)


def test_filtro_objetivo_normaliza_e_filtra(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, selected_objetivo="1") == {dados["alfa_id"]}

        filters = ProjectsListFilters(selected_objetivo="99999")
        query = apply_projects_list_filters(Project.query, filters, admin)
        assert filters.selected_objetivo == ""
        assert {p.id for p in query.all()} == _ids(admin)


def test_filtro_colecao_propria_e_alheia(app, dados):
    with app.app_context():
        comum = db.session.get(User, dados["comum_id"])
        assert _ids(comum, selected_colecao_id=dados["minha_colecao_id"]) == {
            dados["beta_id"]
        }
        assert _ids(comum, selected_colecao_id=dados["colecao_alheia_id"]) == set()


def test_filtro_excluir_colecao(app, dados):
    with app.app_context():
        comum = db.session.get(User, dados["comum_id"])
        assert _ids(comum, excluded_colecao_id=dados["minha_colecao_id"]) == {
            dados["alfa_id"],
            dados["suspenso_id"],
        }


def test_busca_por_titulo_e_id_numerico(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        assert _ids(admin, search_query="Beta") == {dados["beta_id"]}
        assert dados["externo_id"] in _ids(admin, search_query=str(dados["externo_id"]))
        assert _ids(admin, search_query="LFFORA") == {dados["externo_id"]}


def test_combinacao_de_filtros(app, dados):
    with app.app_context():
        admin = db.session.get(User, dados["admin_id"])
        resultado = _ids(
            admin,
            selected_orgao_id=dados["raiz_id"],
            selected_status="Vigente",
            selected_priority="Alta",
        )
        assert resultado == {dados["alfa_id"]}
