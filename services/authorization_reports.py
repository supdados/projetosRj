"""Relatórios de housekeeping de autorização (S4/F3-25 e TR-2).

Duas consultas de LEITURA, sem efeito colateral nenhum sobre acesso:

- ``list_orphan_grants`` — convites ativos cujo concedente perdeu a gestão do
  projeto ou foi soft-deletado (§7 "Grants órfãos"), para revisão manual do
  admin. Com ``project_member`` vazia devolve ``[]``.
- ``usuarios_com_escopo_zerado`` — usuários que ficaram sem NENHUM órgão ativo
  no escopo depois de um sync SIORG desativar unidades (TR-2). O escopo em si
  continua ignorando ``ativo`` (F0-3/F1-4): isto é relatório, não filtro.
"""

from __future__ import annotations

import json
from typing import Any, Sequence, TypedDict

from sqlalchemy.orm import joinedload

from models import OrgaoUnidade, Project, ProjectMember, User, UserOrgao, db
from services.authorization import (
    PAPEL_GESTOR,
    PAPEL_RANK,
    area_project_rank,
    get_user_orgao_role_map,
)
from services.project_membership import active_member_criterion
from time_utils import iso_utc

MOTIVO_CONCEDENTE_REMOVIDO = "concedente_removido"
MOTIVO_CONCEDENTE_SEM_GESTAO = "concedente_sem_gestao"


class OrphanGrant(TypedDict):
    """Convite ativo sem concedente responsável — linha do relatório admin."""

    member_id: int
    project_id: int
    project_titulo: str
    user_id: int
    user_name: str
    granted_by_id: int | None
    granted_by_name: str | None
    motivo: str
    created_at: str | None
    expires_at: str | None


class UsuarioEscopoZerado(TypedDict):
    """Usuário que perdeu todo o escopo ativo no sync (para re-vínculo manual)."""

    id: int
    username: str
    name: str


def list_orphan_grants() -> list[OrphanGrant]:
    """Convites ativos cujo concedente não pode mais geri-los (§7).

    Órfão = concedente soft-deletado (``concedente_removido``) OU sem rank
    gestor no projeto via vínculo de área (``concedente_sem_gestao``). O rank do
    concedente sai de ``area_project_rank``: convite não sustenta convite.

    Exemplo: ``[g["motivo"] for g in list_orphan_grants()]``.
    """
    orfaos: list[OrphanGrant] = []
    for member, project, granter in _active_grant_rows():
        motivo = _motivo_orfao(granter, project)
        if motivo is not None:
            orfaos.append(_orphan_grant(member, project, granter, motivo))
    return orfaos


def _active_grant_rows() -> list[tuple[ProjectMember, Project, User | None]]:
    return (
        db.session.query(ProjectMember, Project, User)
        .join(Project, Project.id == ProjectMember.project_id)
        .outerjoin(User, User.id == ProjectMember.granted_by_id)
        # Eager load do convidado: evita 1 query por linha em _nome_do_membro.
        .options(joinedload(ProjectMember.user))
        .filter(active_member_criterion())
        .order_by(ProjectMember.id)
        .all()
    )


def _motivo_orfao(granter: User | None, project: Project) -> str | None:
    if granter is None or granter.deleted_at is not None:
        return MOTIVO_CONCEDENTE_REMOVIDO
    if area_project_rank(granter, project) < PAPEL_RANK[PAPEL_GESTOR]:
        return MOTIVO_CONCEDENTE_SEM_GESTAO
    return None


def _orphan_grant(
    member: ProjectMember, project: Project, granter: User | None, motivo: str
) -> OrphanGrant:
    return {
        "member_id": member.id,
        "project_id": project.id,
        "project_titulo": project.titulo,
        "user_id": member.user_id,
        "user_name": _nome_do_membro(member),
        "granted_by_id": member.granted_by_id,
        "granted_by_name": granter.name if granter is not None else None,
        "motivo": motivo,
        "created_at": iso_utc(member.created_at),
        "expires_at": iso_utc(member.expires_at),
    }


def _nome_do_membro(member: ProjectMember) -> str:
    convidado = member.user
    if convidado is None:
        return f"usuário {member.user_id}"
    return convidado.name or convidado.username


def usuarios_com_escopo_zerado(
    orgao_ids_desativados: Sequence[int],
) -> list[UsuarioEscopoZerado]:
    """Usuários cujo escopo de área ficou sem nenhum órgão ativo (TR-2).

    Só entram candidatos vinculados a um dos órgãos recém-desativados — para os
    demais nada mudou no sync. Sem desativação, devolve ``[]`` sem consultar
    nada. NÃO altera acesso: quem está aqui continua enxergando o que enxergava.

    Exemplo: ``usuarios_com_escopo_zerado([12, 13])``.
    """
    if not orgao_ids_desativados:
        return []
    ativos = _orgao_ids_ativos()
    return [
        {"id": user.id, "username": user.username, "name": user.name}
        for user in _usuarios_vinculados(orgao_ids_desativados)
        if not (set(get_user_orgao_role_map(user)) & ativos)
    ]


def _orgao_ids_ativos() -> set[int]:
    rows = db.session.query(OrgaoUnidade.id).filter(OrgaoUnidade.ativo.is_(True)).all()
    return {row_id for (row_id,) in rows}


def _usuarios_vinculados(orgao_ids: Sequence[int]) -> list[User]:
    return (
        db.session.query(User)
        .join(UserOrgao, UserOrgao.user_id == User.id)
        .filter(UserOrgao.orgao_id.in_(list(orgao_ids)), User.deleted_at.is_(None))
        .distinct()
        .order_by(User.id)
        .all()
    )


def serializar_escopo_zerado(usuarios: Sequence[UsuarioEscopoZerado]) -> str | None:
    """JSON compacto para ``SiorgSyncLog.usuarios_escopo_zerado`` (``None`` se vazio)."""
    if not usuarios:
        return None
    return json.dumps(list(usuarios), ensure_ascii=False)


def ler_escopo_zerado(payload: Any) -> list[UsuarioEscopoZerado]:
    """Lê de volta a coluna JSON do log; payload corrompido vira lista vazia."""
    if not payload:
        return []
    try:
        dados = json.loads(payload)
    except (TypeError, ValueError):
        return []
    return dados if isinstance(dados, list) else []
