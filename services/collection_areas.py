"""Áreas dos projetos de cada coleção — a pílula "N áreas" da capa do card.

Módulo próprio porque ``services/project_collections.py`` já passa do teto de
tamanho; aqui fica só o agregado por área, em 1 query para N coleções (o
índice tem orçamento fixo de queries em
``tests/routes/test_read_materialization.py``).
"""

from __future__ import annotations

from typing import Iterable, Optional, TypedDict

from sqlalchemy import func

from models import OrgaoUnidade, Project, ProjectCollectionItem, User, db
from services.authorization import apply_project_visibility


class AreaDaColecao(TypedDict):
    """Uma área da coleção: sigla do órgão do projeto (``None`` = sem órgão)."""

    sigla: Optional[str]
    projetos: int


def areas_por_colecao(
    collection_ids: Iterable[int], viewer: User
) -> dict[int, list[AreaDaColecao]]:
    """``{collection_id: [{sigla, projetos}, ...]}`` contando SÓ projetos visíveis.

    Ordem: mais projetos primeiro, empate pela sigla (sem órgão por último) —
    a mesma do tooltip da capa. Coleção sem projeto visível sai com lista
    vazia. Exemplo: ``areas_por_colecao([c.id for c in colecoes], g.user)``.
    """
    ids = [int(collection_id) for collection_id in collection_ids]
    areas: dict[int, list[AreaDaColecao]] = {collection_id: [] for collection_id in ids}
    if not ids:
        return areas
    for collection_id, sigla, projetos in _area_rows(ids, viewer):
        areas[collection_id].append({"sigla": sigla, "projetos": int(projetos)})
    for lista in areas.values():
        lista.sort(key=_ordem_da_area)
    return areas


def _ordem_da_area(area: AreaDaColecao) -> tuple[int, bool, str]:
    sigla = area["sigla"]
    return (-area["projetos"], sigla is None, sigla or "")


def _area_rows(ids: list[int], viewer: User) -> list[tuple[int, Optional[str], int]]:
    query = (
        db.session.query(
            ProjectCollectionItem.collection_id,
            OrgaoUnidade.sigla,
            func.count(func.distinct(Project.id)),
        )
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(OrgaoUnidade, OrgaoUnidade.id == Project.orgao_id)
        .filter(ProjectCollectionItem.collection_id.in_(ids))
        # Pelo id também: duas unidades com a mesma sigla não se fundem.
        .group_by(
            ProjectCollectionItem.collection_id, OrgaoUnidade.id, OrgaoUnidade.sigla
        )
    )
    return [tuple(row) for row in apply_project_visibility(query, viewer).all()]
