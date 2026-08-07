"""Regressão do batch de escopo em ``_accessible_project_ids`` (Sprint 4).

O check por projeto via ``user_can_access_project`` recomputava o subtree de
órgãos (query em OrgaoClosure) a cada projeto — N+1 no GET /api/notificacoes.
Hoje a resolução vive em ``services.authorization`` com os mapas de área e de
convite cacheados em ``g``; o invariante medido aqui deixou de ser "quantas
vezes o resolver é chamado" e passou a ser o custo em statements: filtrar N
projetos custa as MESMAS queries que filtrar um (partindo de cache frio).
"""

from flask import g

from models import Project, User, db
from routes.notifications import _accessible_project_ids
from services.authorization import (
    COLLECTION_RANK_CACHE_ATTR,
    MEMBERSHIP_MAP_CACHE_ATTR,
    ROLE_MAP_CACHE_ATTR,
)
from tests.sql_query_counter import SqlQueryCounter


def _custo_com_cache_frio(project_ids: set[int]) -> tuple[set[int], int]:
    """Roda o filtro com os caches de ``g`` derrubados e conta os statements."""
    g.pop(ROLE_MAP_CACHE_ATTR, None)
    g.pop(MEMBERSHIP_MAP_CACHE_ATTR, None)
    g.pop(COLLECTION_RANK_CACHE_ATTR, None)
    with SqlQueryCounter(db.engine) as counter:
        acessiveis = _accessible_project_ids(project_ids)
    return acessiveis, counter.total


def _add_projetos(quantidade: int, orgao_id: int) -> set[int]:
    ids = set()
    for numero in range(quantidade):
        projeto = Project(
            titulo=f"Projeto lote {numero}",
            orgao_id=orgao_id,
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(projeto)
        db.session.flush()
        ids.add(projeto.id)
    return ids


def _project_without_orgao() -> Project:
    project = Project(
        titulo="Projeto sem órgão",
        orgao_id=None,
        status="Vigente",
        objetivo_id=1,
        resultado_esperado_id=1,
    )
    db.session.add(project)
    db.session.flush()
    return project


def test_non_admin_scope_matches_user_can_access_project(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        orphan = _project_without_orgao()
        requested = {
            seed_data["project_id"],
            seed_data["foreign_project_id"],
            orphan.id,
        }
        assert _accessible_project_ids(requested) == {seed_data["project_id"]}


def test_admin_sees_all_existing_projects(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["admin_id"])
        requested = {seed_data["project_id"], seed_data["foreign_project_id"], 999_999}
        assert _accessible_project_ids(requested) == {
            seed_data["project_id"],
            seed_data["foreign_project_id"],
        }


def test_escopo_de_muitos_projetos_custa_o_mesmo_que_de_um(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        # Vínculos do usuário fora do contador: lazy load é do fixture, não do filtro.
        list(g.user.orgaos)
        do_lote = _add_projetos(20, seed_data["auditoria_orgao_id"])
        muitos = do_lote | {
            seed_data["project_id"],
            seed_data["project_complete_id"],
            seed_data["foreign_project_id"],
        }

        acessiveis, custo_muitos = _custo_com_cache_frio(muitos)
        _, custo_um = _custo_com_cache_frio({seed_data["project_id"]})

        assert acessiveis == do_lote | {
            seed_data["project_id"],
            seed_data["project_complete_id"],
        }
        assert custo_muitos == custo_um


def test_empty_input_short_circuits_without_queries(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        acessiveis, custo = _custo_com_cache_frio(set())
        assert acessiveis == set()
        assert custo == 0
