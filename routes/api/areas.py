"""Endpoint JSON com TODAS as áreas ativas (picker de responsáveis de etapa).

Diferente de ``GET /api/orgaos/escopo`` (escopado por subtree) e de
``GET /api/admin/orgaos/opcoes`` (admin-only), este endpoint lista o catálogo
COMPLETO de ``OrgaoUnidade`` ativas para qualquer usuário logado — a busca é
100% client-side no ``AreaResponsavelPicker`` (mesmo padrão do AssigneePicker).

Anexa ao ``main_bp`` ÚNICO; NÃO cria blueprint novo.

Payload inclui ``pai_id`` para permitir montagem de árvore client-side
(mesmo padrão de ``serialize_orgao_option``, usado pelo picker de Responsável
da etapa).
"""

from __future__ import annotations

from flask import Response

from models import OrgaoUnidade

from ..blueprint import main_bp
from .envelope import ok
from .negotiation import api_login_required


@main_bp.route("/api/areas", methods=["GET"])
@api_login_required
def api_areas_listar() -> Response | tuple[Response, int]:
    """Lista TODAS as áreas (OrgaoUnidade) ativas, ordenadas por sigla.

    Returns:
        ``ok({"areas": [{"id", "sigla", "nome", "pai_id"}, ...]})`` (200); 401 sem sessão.
    """
    areas = (
        OrgaoUnidade.query.filter(OrgaoUnidade.ativo.is_(True))
        .order_by(OrgaoUnidade.sigla)
        .all()
    )
    return ok(
        {
            "areas": [
                {"id": o.id, "sigla": o.sigla, "nome": o.nome, "pai_id": o.pai_id}
                for o in areas
            ]
        }
    )
