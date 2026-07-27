"""Superfície de membership de projeto consumida pela API (S4/F3-10 e F3-13).

Três responsabilidades, todas de LEITURA (nenhuma escreve em ``project_member``):

- ``project_permission_flags`` / ``project_access_via`` — o que a §6.4 manda a
  SPA receber pronto do servidor, derivado dos mapas já cacheados em ``g``
  (``services.authorization``): zero query por projeto serializado.
- ``list_inherited_members`` — os membros herdados do vínculo de área do projeto
  (§6.5), read-only e em UMA query.
- ``convites_habilitados`` / ``active_member_criterion`` — a flag e o predicado
  de convite ativo compartilhados por rotas e relatórios.

Nenhuma checagem de admin inline (grep-gate F0-6): o piso do admin chega por
``area_project_rank(...) >= ADMIN_RANK``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from flask import current_app, has_app_context
from sqlalchemy import and_, or_

from models import OrgaoClosure, OrgaoUnidade, ProjectMember, User, UserOrgao, db
from services.authorization import (
    ADMIN_RANK,
    PAPEL_GESTOR,
    PAPEL_RANK,
    area_project_rank,
    get_active_membership_map,
    user_can_edit_project,
    user_can_manage_project,
)
from time_utils import utc_now

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

ACCESS_VIA_ADMIN = "admin"
ACCESS_VIA_AREA = "area"
ACCESS_VIA_CONVITE = "convite"
ACCESS_VIA_AMBOS = "ambos"


class ProjectPermissionFlags(TypedDict):
    """Flags autoritativas de ação sobre UM projeto, para a SPA não recalcular."""

    can_edit: bool
    can_manage: bool
    can_manage_members: bool


class InheritedMember(TypedDict):
    """Membro que enxerga o projeto pelo vínculo de área (nunca por convite)."""

    user_id: int
    name: str
    username: str
    papel: str
    via_orgao_id: int
    via_orgao_sigla: str


def convites_habilitados() -> bool:
    """True quando ``CONVITES_HABILITADOS`` está ligada (default off, F3-23).

    Fora de contexto de aplicação (script, worker) devolve ``False``: a leitura
    de convites já gravados NÃO passa por aqui, só a gestão deles.
    """
    if not has_app_context():
        return False
    return bool(current_app.config.get("CONVITES_HABILITADOS", False))


def user_can_manage_members(user: Any, project: Any) -> bool:
    """True quando o usuário pode convidar/revogar neste projeto.

    Rank >= gestor obtido VIA VÍNCULO DE ÁREA (ou o piso do admin) — convite
    jamais concede gestão (auto-promoção do Redmine #11075) — e só com a flag
    ``CONVITES_HABILITADOS`` ligada.
    """
    if not convites_habilitados():
        return False
    return area_project_rank(user, project) >= PAPEL_RANK[PAPEL_GESTOR]


def project_permission_flags(user: Any, project: Any) -> ProjectPermissionFlags:
    """Flags de ação do usuário no projeto (§6.4), sem custo de query.

    Exemplo: ``project_permission_flags(g.user, projeto)["can_edit"]``.
    """
    return {
        "can_edit": user_can_edit_project(user, project),
        "can_manage": user_can_manage_project(user, project),
        "can_manage_members": user_can_manage_members(user, project),
    }


def project_access_via(user: Any, project: Any) -> str | None:
    """Via de acesso ao projeto: ``admin``/``area``/``convite``/``ambos``.

    ``None`` quando o usuário não alcança o projeto. ``admin`` vence tudo (o
    badge "Convidado" da SPA não aparece para admin); quem tem vínculo de área E
    convite ativo sai como ``ambos``, que a SPA também trata como convidado.
    """
    rank_de_area = area_project_rank(user, project)
    if rank_de_area >= ADMIN_RANK:
        return ACCESS_VIA_ADMIN
    convidado = getattr(project, "id", None) in get_active_membership_map(user)
    if rank_de_area > 0:
        return ACCESS_VIA_AMBOS if convidado else ACCESS_VIA_AREA
    return ACCESS_VIA_CONVITE if convidado else None


def active_member_criterion() -> "ColumnElement[bool]":
    """Predicado SQL de convite ATIVO: não revogado e não expirado (lazy)."""
    return and_(
        ProjectMember.revoked_at.is_(None),
        or_(ProjectMember.expires_at.is_(None), ProjectMember.expires_at > utc_now()),
    )


def list_inherited_members(project: Any) -> list[InheritedMember]:
    """Membros herdados pelo órgão do projeto — READ-ONLY, UMA query (§6.5).

    Ancestrais-ou-próprio de ``project.orgao_id`` via ``OrgaoClosure``, com os
    vínculos ``user_orgao`` de usuários ativos. Nunca vira linha em
    ``project_member``: quem herda só é editável na tela de admin de usuários.
    Usuário vinculado a mais de um ancestral aparece UMA vez, com o vínculo de
    maior papel (mesma resolução ``max()`` do role map).

    Exemplo: ``[m["via_orgao_sigla"] for m in list_inherited_members(projeto)]``.
    """
    orgao_id = getattr(project, "orgao_id", None)
    if not isinstance(orgao_id, int):
        return []
    melhores: dict[int, InheritedMember] = {}
    for row in _inherited_member_rows(orgao_id):
        membro = _inherited_member(row)
        atual = melhores.get(membro["user_id"])
        if atual is None or _papel_rank(membro) > _papel_rank(atual):
            melhores[membro["user_id"]] = membro
    return sorted(melhores.values(), key=lambda m: (m["name"] or "", m["user_id"]))


def _inherited_member_rows(orgao_id: int) -> list[Any]:
    ancestrais = db.session.query(OrgaoClosure.ancestor_id).filter(
        OrgaoClosure.descendant_id == orgao_id
    )
    return (
        db.session.query(
            User.id,
            User.name,
            User.username,
            UserOrgao.papel,
            OrgaoUnidade.id,
            OrgaoUnidade.sigla,
        )
        .join(UserOrgao, UserOrgao.user_id == User.id)
        .join(OrgaoUnidade, OrgaoUnidade.id == UserOrgao.orgao_id)
        .filter(
            User.deleted_at.is_(None),
            # A closure pode não ter a linha depth 0 (órgão criado pela tela de
            # admin, sem rebuild): o próprio órgão entra explicitamente.
            or_(UserOrgao.orgao_id == orgao_id, UserOrgao.orgao_id.in_(ancestrais)),
        )
        .all()
    )


def _inherited_member(row: Any) -> InheritedMember:
    user_id, name, username, papel, via_orgao_id, via_orgao_sigla = row
    return {
        "user_id": user_id,
        "name": name,
        "username": username,
        # Vínculo legado anterior ao backfill vale gestor (mesma leitura do role map).
        "papel": papel or PAPEL_GESTOR,
        "via_orgao_id": via_orgao_id,
        "via_orgao_sigla": via_orgao_sigla,
    }


def _papel_rank(membro: InheritedMember) -> int:
    return PAPEL_RANK.get(membro["papel"], 0)
