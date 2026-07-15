"""Endpoints admin da integração SIORG (status + disparo manual do sync).

CONTRATO CRU (sem o envelope ``{ok, data}``): o frontend
(``lib/api/adminOrgaos.ts``) consome estes corpos diretamente —
``GET /api/admin/siorg/status`` → ``{"configurado", "ultima_sincronizacao"}`` e
``POST /api/admin/siorg/sync`` → 200 ``{"status": "sucesso", ...}`` |
409/502/503 ``{"error": "..."}``.
"""

from __future__ import annotations

from typing import Any

from flask import Response, current_app, g, jsonify

from models import SiorgSyncLog
from services.siorg_client import SiorgApiError, siorg_client_from_config
from services.siorg_sync import SiorgSyncEmAndamento, executar_sync_siorg

from ..blueprint import main_bp
from .negotiation import api_admin_required


def _iso_or_none(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_sync_log(log: SiorgSyncLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "status": log.status,
        "iniciado_em": _iso_or_none(log.iniciado_em),
        "finalizado_em": _iso_or_none(log.finalizado_em),
        "versao_global": log.versao_global,
        "criadas": log.criadas,
        "atualizadas": log.atualizadas,
        "desativadas": log.desativadas,
        "erro": log.erro,
        "disparado_por_nome": log.disparado_por.name if log.disparado_por else None,
    }


@main_bp.route("/api/admin/siorg/status", methods=["GET"])
@api_admin_required
def api_admin_siorg_status() -> Response:
    """Configuração da integração + última sincronização registrada."""
    configurado = bool(str(current_app.config.get("SIORG_API_KEY", "") or "").strip())
    ultimo = SiorgSyncLog.query.order_by(
        SiorgSyncLog.iniciado_em.desc(), SiorgSyncLog.id.desc()
    ).first()
    return jsonify(
        {
            "configurado": configurado,
            "ultima_sincronizacao": (
                _serialize_sync_log(ultimo) if ultimo is not None else None
            ),
        }
    )


@main_bp.route("/api/admin/siorg/sync", methods=["POST"])
@api_admin_required
def api_admin_siorg_sync() -> Response | tuple[Response, int]:
    """Dispara o full-sync SIORG→ProjetosRJ (lock anti-concorrência no banco)."""
    # Config ausente é erro do operador, não indisponibilidade do SIORG (502).
    if not str(current_app.config.get("SIORG_API_KEY", "") or "").strip():
        return (
            jsonify(
                {"error": "Integração SIORG não configurada (defina SIORG_API_KEY)"}
            ),
            503,
        )
    try:
        client = siorg_client_from_config(current_app.config)
        log = executar_sync_siorg(
            client,
            g.user.id,
            codigo_raiz=int(current_app.config.get("SIORG_RAIZ_CODIGO", 2)),
        )
    except SiorgSyncEmAndamento as exc:
        current_app.logger.warning(
            "siorg_sync bloqueado por lock", extra={"detalhe": str(exc)}
        )
        return jsonify({"error": str(exc)}), 409
    except SiorgApiError as exc:
        current_app.logger.error(
            "siorg_sync falhou na API do SIORG",
            extra={"detalhe": str(exc), "status_code": exc.status_code},
        )
        return jsonify({"error": f"SIORG indisponível: {exc}"}), 502

    current_app.logger.info(
        "siorg_sync concluído",
        extra={
            "sync_log_id": log.id,
            "criadas": log.criadas,
            "atualizadas": log.atualizadas,
            "desativadas": log.desativadas,
        },
    )
    return jsonify(
        {
            "status": "sucesso",
            "criadas": log.criadas,
            "atualizadas": log.atualizadas,
            "desativadas": log.desativadas,
            "versao_global": log.versao_global,
        }
    )
