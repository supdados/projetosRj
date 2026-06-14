"""Helpers de CRUD de usuários (parse de órgãos/CPF e árvore de órgãos para o
form) compartilhados com a API da SPA (``routes/api/admin_users.py``).

As rotas Jinja ``/admin/users*`` (list/add/edit/delete/remove-cpf) foram
cortadas na migração SPA — o CRUD vive em ``/admin/usuarios*`` (SPA) +
``/api/admin/usuarios*`` (envelope). Este módulo permanece só pelos helpers.
"""

from models import OrgaoUnidade, db
from services.govbr_oidc import normalize_cpf

from .orgao_tree import compute_orgao_depth


def _list_orgaos_with_depth():
    """[(orgao_id, sigla, nome, depth)] ordenado por (depth, sigla) para UI de arvore."""
    orgaos = OrgaoUnidade.query.filter(OrgaoUnidade.ativo.is_(True)).all()
    rows = [(o.id, o.sigla, o.nome, compute_orgao_depth(o)) for o in orgaos]
    rows.sort(key=lambda row: (row[3], row[1].lower()))
    return rows


def _parse_selected_orgaos(raw_ids):
    selected_ids = []
    invalid = []
    seen = set()
    for raw in raw_ids:
        try:
            orgao_id = int(raw)
        except (TypeError, ValueError):
            invalid.append(raw)
            continue
        if orgao_id in seen:
            continue
        orgao = db.session.get(OrgaoUnidade, orgao_id)
        if orgao is None:
            invalid.append(str(raw))
            continue
        seen.add(orgao_id)
        selected_ids.append(orgao_id)
    return selected_ids, invalid


def _parse_cpf_govbr(raw_cpf):
    if raw_cpf is None or not str(raw_cpf).strip():
        return None, None
    try:
        return normalize_cpf(raw_cpf), None
    except ValueError as exc:
        return None, str(exc)
