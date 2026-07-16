"""Endpoints JSON read-only de Órgãos (árvore) para a SPA Admin.

A estrutura organizacional passou a ser espelho do SIORG-RJ
(``services/siorg_sync.py`` + ``routes/api/admin_siorg.py``): as rotas de
escrita (criar/editar/excluir/mover/reordenar/toggle de unidades e todo o CRUD
de tipos) foram CORTADAS, assim como os GETs do catálogo local de tipos e os
campos ``tipos``/``tipo_rank``/``candidatos_pai`` das respostas — o catálogo
de 8 níveis não descreve a taxonomia SIORG e o frontend não os lê mais. Restam
os GETs de visualização, protegidos por ``api_admin_required`` (401 sem
sessão, 403 para não-admin).

Cada nó da árvore serializa ``codigo_externo`` (string do código SIORG;
``null`` = unidade local "não oficial", ex.: ECENTRAL). Os GETs NÃO chamam mais
``backfill_orgao_tipo_ids``: o sync grava ``tipo_id=None`` (tipo = taxonomia
SIORG na coluna ``tipo``) e o backfill desfaria isso em cada leitura.
"""

from __future__ import annotations

from flask import Response

from models import OrgaoUnidade, db
from models.orgao import MAX_DEPTH

from ..admin_users import _list_orgaos_with_parent
from ..blueprint import main_bp
from .envelope import fail, ok
from .negotiation import api_admin_required
from .serializers import serialize_orgao_form, serialize_orgao_node


@main_bp.route("/api/admin/orgaos", methods=["GET"])
@api_admin_required
def api_admin_orgaos_tree() -> Response | tuple[Response, int]:
    """Árvore completa de órgãos (visualização read-only espelhando o SIORG).

    Returns:
        Envelope ``{"ok": true, "data": {"arvore", "max_depth", "total"}}``
        com HTTP 200.
    """
    raizes = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id.is_(None))
        .order_by(OrgaoUnidade.ordem, OrgaoUnidade.sigla)
        .all()
    )
    total = OrgaoUnidade.query.count()
    return ok(
        {
            "arvore": [serialize_orgao_node(raiz) for raiz in raizes],
            "max_depth": MAX_DEPTH,
            "total": total,
        }
    )


@main_bp.route("/api/admin/orgaos/opcoes", methods=["GET"])
@api_admin_required
def api_admin_orgaos_opcoes() -> Response | tuple[Response, int]:
    """Opções de órgãos (ativos, achatadas) para o seletor do form de usuário.

    Reusa ``_list_orgaos_with_parent`` (``routes/admin_users.py``): somente
    órgãos ativos, ordenados por sigla; a árvore é montada por ``pai_id`` no
    client.

    Returns:
        Envelope ``{"ok": true, "data": [{"id", "sigla", "nome", "pai_id"}, ...]}``
        com HTTP 200; 401 JSON sem sessão; 403 JSON para não-admin.
    """
    opcoes = [
        {"id": orgao_id, "sigla": sigla, "nome": nome, "pai_id": pai_id}
        for orgao_id, sigla, nome, pai_id in _list_orgaos_with_parent()
    ]
    return ok(opcoes)


@main_bp.route("/api/admin/orgaos/<int:orgao_id>", methods=["GET"])
@api_admin_required
def api_admin_orgaos_detail(orgao_id: int) -> Response | tuple[Response, int]:
    """Dados de um órgão (read-only).

    Args:
        orgao_id: ID do órgão a carregar.

    Returns:
        Envelope com ``{"orgao", "is_root"}``; ``fail(..., 404, "not_found")``
        quando não existe.
    """
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return fail("Órgão não encontrado.", status=404, code="not_found")
    return ok(
        {
            "orgao": serialize_orgao_form(orgao),
            "is_root": orgao.pai_id is None,
        }
    )
