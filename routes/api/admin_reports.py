"""Relatórios administrativos de autorização (S4/F3-25).

Superfície de LEITURA do housekeeping de convites: expõe
``services/authorization_reports.list_orphan_grants`` para a tela admin da SPA.
Sem gate de ``CONVITES_HABILITADOS``: a flag gate a GESTÃO de convites (§7);
revisar grants já gravados é exatamente o caso de flag recém-desligada.
"""

from __future__ import annotations

from flask import Response

from services.authorization_reports import list_orphan_grants

from ..blueprint import main_bp
from .envelope import fail_internal, ok
from .negotiation import api_admin_required


@main_bp.route("/api/admin/relatorios/grants-orfaos", methods=["GET"])
@api_admin_required
def api_admin_grants_orfaos() -> Response | tuple[Response, int]:
    """Convites ativos cujo concedente perdeu a gestão (§7 "Grants órfãos").

    Returns:
        ``{"grants": [OrphanGrant, ...]}`` no envelope canônico; com
        ``project_member`` vazia devolve ``{"grants": []}``.
    """
    try:
        return ok({"grants": list_orphan_grants()})
    except Exception as exc:
        return fail_internal(exc, "listar grants órfãos")
