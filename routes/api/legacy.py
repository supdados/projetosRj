"""Endpoints JSON pré-existentes do portal.

Este módulo preserva, sem alteração de path nem de lógica, as rotas que já
existiam em ``routes/api.py`` antes da migração para o pacote ``routes.api``.
As funções continuam anexadas a ``main_bp`` (logo ``url_for("main.<fn>")`` e os
endpoints registrados permanecem idênticos). Novos endpoints da SPA devem usar
o envelope canônico (``routes/api/envelope.py``); estes legados ainda retornam
payloads crus/`{"error": ...}` por compatibilidade com o frontend Jinja atual.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app, g, jsonify, request

from models import Project, StageTemplate, StageTemplateItem
from sqlalchemy import func
from catalogs.objectives import (
    OBJETIVO_IDS,
    RESULTADO_IDS,
    get_indicadores_for_resultado,
    get_resultados_for_objetivo,
)

from ..blueprint import main_bp
from ..decorators import login_required
from ..orgao_scope import get_user_orgao_subtree_ids
from ..shared import get_or_404


@main_bp.route("/api/resultados/<int:objetivo_id>")
@login_required
def get_resultados(objetivo_id):
    if objetivo_id not in OBJETIVO_IDS:
        return jsonify({"error": "Objetivo não encontrado"}), 404

    return jsonify(get_resultados_for_objetivo(objetivo_id))


@main_bp.route("/api/indicadores/<int:resultado_id>")
@login_required
def get_indicadores(resultado_id):
    if resultado_id not in RESULTADO_IDS:
        return jsonify({"error": "Resultado esperado não encontrado"}), 404

    return jsonify(get_indicadores_for_resultado(resultado_id))


# --- API para Modelos de Etapas ---


@main_bp.route("/api/templates")
@login_required
def get_templates():
    from models import db

    stats_rows = (
        db.session.query(
            StageTemplateItem.templateId,
            func.count(StageTemplateItem.id),
            func.coalesce(func.sum(StageTemplateItem.duration_days), 0),
        )
        .group_by(StageTemplateItem.templateId)
        .all()
    )
    stats_by_template = {tid: (count, int(total)) for tid, count, total in stats_rows}

    templates = StageTemplate.query.order_by(StageTemplate.name).all()
    payload = []
    for t in templates:
        count, total = stats_by_template.get(t.id, (0, 0))
        payload.append(
            {
                "id": t.id,
                "name": t.name,
                "stage_count": count,
                "total_duration_days": total,
            }
        )
    return jsonify(payload)


@main_bp.route("/api/templates/<int:template_id>")
@login_required
def get_template_stages(template_id):
    template = get_or_404(StageTemplate, template_id)
    stages = [
        {"name": item.name, "order": item.order, "duration": item.duration_days}
        for item in template.items
    ]
    return jsonify(stages)


@main_bp.route("/api/projetos_usuario", methods=["GET"])
@login_required
def get_user_projects_api():
    """API para obter projetos do usuário para dropdown"""
    if g.user.is_admin:
        projects = Project.query.order_by(Project.titulo).all()
    else:
        subtree_ids = get_user_orgao_subtree_ids(g.user)
        if subtree_ids:
            projects = (
                Project.query.filter(Project.orgao_id.in_(subtree_ids))
                .order_by(Project.titulo)
                .all()
            )
        else:
            projects = []

    return jsonify(
        [
            {
                "id": p.id,
                "titulo": p.titulo,
                "orgao_sigla": p.orgao_ref.sigla if p.orgao_ref else None,
            }
            for p in projects
        ]
    )


@main_bp.route("/api/chatbot-token", methods=["GET"])
@login_required
def get_chatbot_token():
    if not current_app.config.get("CHATBOT_ENABLED"):
        return jsonify({"error": "Chatbot desabilitado"}), 404

    chatbot_base_url = (
        str(current_app.config.get("CHATBOT_BASE_URL", "")).strip().rstrip("/")
    )
    portal_api_key = str(current_app.config.get("CHATBOT_PORTAL_API_KEY", "")).strip()
    timeout_seconds = int(current_app.config.get("CHATBOT_TIMEOUT_SECONDS", 10) or 10)

    if not chatbot_base_url or not portal_api_key:
        current_app.logger.error("Configuracao do chatbot incompleta no portal.")
        return jsonify({"error": "Chatbot indisponivel"}), 503

    portal_origin = request.host_url.rstrip("/")
    upstream_request = Request(
        f"{chatbot_base_url}/api/token",
        data=b"",
        method="POST",
        headers={
            "X-Portal-API-Key": portal_api_key,
            "X-Portal-Origin": portal_origin,
        },
    )

    try:
        with urlopen(upstream_request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        current_app.logger.warning("Chatbot token upstream retornou HTTP %s", exc.code)
        return jsonify({"error": "Falha ao obter token do chatbot"}), 502
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        current_app.logger.warning("Falha ao obter token do chatbot: %s", exc)
        return jsonify({"error": "Falha ao obter token do chatbot"}), 502

    token = str(payload.get("token") or "").strip()
    expires_in = payload.get("expires_in")
    if not token or not isinstance(expires_in, int):
        current_app.logger.warning("Payload invalido ao obter token do chatbot.")
        return jsonify({"error": "Resposta invalida do chatbot"}), 502

    return jsonify({"token": token, "expires_in": expires_in})
