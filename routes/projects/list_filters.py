"""Filtros da Lista de Projetos aplicados como função pura sobre a query.

Extraído VERBATIM de ``build_projects_list_context`` (views.py) para ser
compartilhado com o export (``GET /api/projetos/exportar``).
"""

from dataclasses import dataclass

from flask_sqlalchemy.query import Query

from models import Project, ProjectCollection, ProjectCollectionItem, User, db
from routes.orgao_scope import expand_orgao_filter_ids
from routes.shared import (
    parse_abep_indicator_filter,
    parse_db_integer_id,
    parse_objetivo_filter,
    project_orgao_search_filter,
)
from services.atraso import projeto_atrasado_criterion
from services.authorization import project_visibility_criterion


@dataclass
class ProjectsListFilters:
    """Filtros da listagem de projetos; defaults (ex.: status Vigente) são da rota."""

    selected_orgao_id: int | None = None
    apenas_orgao: bool = False
    selected_status: str | None = None
    selected_priority: str | None = None
    selected_atraso: str | None = None
    selected_special_project: str | None = None
    selected_delivery_type: str | None = None
    selected_abep_indicator: str | None = None
    selected_objetivo: str | None = None
    selected_colecao_id: int | None = None
    excluded_colecao_id: int | None = None
    search_query: str | None = ""


def _colecao_project_ids_subquery(collection_id: int, user: User) -> Query:
    """Ids dos projetos da coleção, SÓ se ela pertence ao usuário informado.

    Coleção de outro dono devolve subquery vazia (filtro sem resultado) em vez de
    erro — a existência da coleção alheia não vaza pela lista.
    """
    return (
        db.session.query(ProjectCollectionItem.project_id)
        .join(
            ProjectCollection,
            ProjectCollection.id == ProjectCollectionItem.collection_id,
        )
        .filter(
            ProjectCollection.id == collection_id,
            ProjectCollection.owner_user_id == user.id,
        )
    )


def _apply_scope_filters(
    query: Query, filters: ProjectsListFilters, user: User
) -> Query:
    if not user.is_admin:
        query = query.filter(project_visibility_criterion(user))
    if filters.selected_orgao_id is not None:
        subtree_ids = expand_orgao_filter_ids(
            filters.selected_orgao_id, incluir_descendentes=not filters.apenas_orgao
        )
        if subtree_ids:
            query = query.filter(Project.orgao_id.in_(subtree_ids))
    if filters.selected_colecao_id is not None:
        query = query.filter(
            Project.id.in_(
                _colecao_project_ids_subquery(filters.selected_colecao_id, user)
            )
        )
    if filters.excluded_colecao_id is not None:
        query = query.filter(
            ~Project.id.in_(
                _colecao_project_ids_subquery(filters.excluded_colecao_id, user)
            )
        )
    return query


def _apply_attribute_filters(query: Query, filters: ProjectsListFilters) -> Query:
    if filters.selected_priority and filters.selected_priority != "":
        query = query.filter(Project.prioridade == filters.selected_priority)
    if filters.selected_status and filters.selected_status != "":
        query = query.filter(Project.status == filters.selected_status)
    if filters.selected_special_project and filters.selected_special_project != "":
        query = query.filter(
            Project.special_project == filters.selected_special_project
        )
    if filters.selected_delivery_type and filters.selected_delivery_type != "":
        query = query.filter(Project.delivery_type == filters.selected_delivery_type)
    filters.selected_abep_indicator = parse_abep_indicator_filter(
        filters.selected_abep_indicator
    )
    if filters.selected_abep_indicator:
        query = query.filter(Project.abep_indicator == filters.selected_abep_indicator)
    objetivo_filter_id = parse_objetivo_filter(filters.selected_objetivo)
    if filters.selected_objetivo and objetivo_filter_id is None:
        filters.selected_objetivo = ""
    if filters.selected_objetivo and objetivo_filter_id is not None:
        query = query.filter(Project.objetivo_id == objetivo_filter_id)
    return query


def _apply_search_filter(query: Query, filters: ProjectsListFilters) -> Query:
    if not filters.search_query:
        return query
    search_pattern = f"%{filters.search_query}%"
    search_id = parse_db_integer_id(filters.search_query)
    text_filters = db.or_(
        Project.titulo.ilike(search_pattern),
        project_orgao_search_filter(search_pattern),
        Project.abep_indicator.ilike(search_pattern),
    )
    return query.filter(
        db.or_(Project.id == search_id, text_filters)
        if search_id is not None
        else text_filters
    )


def _apply_atraso_filter(query: Query, filters: ProjectsListFilters) -> Query:
    if filters.selected_atraso in ("atrasado", "no_prazo"):
        # Atraso só é definido para projetos vigentes (semântica preservada).
        atrasado = projeto_atrasado_criterion()
        query = query.filter(Project.status == "Vigente")
        query = query.filter(
            atrasado if filters.selected_atraso == "atrasado" else ~atrasado
        )
    elif filters.selected_atraso:
        # Valor desconhecido preservava lista vazia na versão em Python.
        query = query.filter(db.false())
    return query


def apply_projects_list_filters(
    query: Query, filters: ProjectsListFilters, user: User
) -> Query:
    """Aplica os filtros da Lista de Projetos sobre ``query`` e a devolve.

    Normaliza ``selected_abep_indicator``/``selected_objetivo`` in-place em
    ``filters`` (o chamador ecoa os valores normalizados no contexto).
    """
    query = _apply_scope_filters(query, filters, user)
    query = _apply_attribute_filters(query, filters)
    query = _apply_search_filter(query, filters)
    return _apply_atraso_filter(query, filters)
