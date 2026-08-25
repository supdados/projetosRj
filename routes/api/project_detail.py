"""Endpoints JSON do Detalhe de Projeto (Fase 5a) consumidos pela SPA.

Telas de detalhe do projeto: leitura completa do cabeçalho, edição inline dos
campos do projeto (incluindo status/prioridade) e a seção de ETAPAS. As tarefas
de cada etapa aparecem SOMENTE LEITURA (contagem + lista simples); a mutação de
tarefas/drawer fica para a Fase 5b e as reuniões Google para a Fase 6 (quando
presentes no payload, são renderizadas read-only).

Três endpoints, todos no envelope canônico, protegidos por ``api_login_required``
(401 JSON) e por ``require_project_rank`` no rank ``leitor`` — 404 idêntico para
projeto inexistente e para projeto invisível ao usuário (S5/F4-2b):

    - ``GET  /api/projetos/<id>/detalhe``        — payload completo do detalhe.
    - ``POST /api/projetos/<id>/inline``         — edição inline de campos do
      projeto, reusando ``apply_project_inline_changes`` (mesma validação da rota
      Jinja); erros de validação => 422 (``validation``); órgão sem permissão =>
      403 (``forbidden``).
    - ``GET  /api/projetos/<id>/tarefas-etapa``  — lista SOMENTE LEITURA das
      tarefas de uma etapa (reusa a query de ``routes/projects/stage_tasks.py``).

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo e
NÃO altera as rotas Jinja/legadas (coexistência via strangler).
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request

from catalogs.abep import ABEP_INDICADORES_OPTIONS
from catalogs.inventario import orgao_allows_inventario
from models import Project, Task, db

from services.authorization import PAPEL_LEITOR, require_project_rank
from services.project_membership import project_permission_flags
from services.project_relations import listar_relacionados_payload

from ..blueprint import main_bp
from ..calendars.helpers import _connection_for_current_user
from ..orgao_scope import scoped_orgao_options
from ..projects.ajax import ProjectInlineError, apply_project_inline_changes
from ..shared import log_project_action
from .envelope import fail, ok
from .etapa_payload import project_etapas_payload
from .negotiation import api_login_required
from .serializers import serialize_project_detail, serialize_task_card

# Status selecionáveis no dropdown. "Finalizado" NUNCA é ofertado aqui: a única
# transição para Finalizado é POST /api/projetos/<id>/concluir (botão Concluir).
_STATUS_OPTIONS = [
    {"value": "Vigente", "label": "Vigente"},
    {"value": "Suspenso", "label": "Suspenso"},
]
_PRIORIDADE_OPTIONS = [
    {"value": "baixa", "label": "Baixa"},
    {"value": "media", "label": "Média"},
    {"value": "alta", "label": "Alta"},
    {"value": "urgente", "label": "Urgente"},
]
_SPECIAL_PROJECT_OPTIONS = ["ABEP", "TCE", "Fórum de simplificação"]
_DELIVERY_TYPE_OPTIONS = [
    "Sistema",
    "Painel",
    "Norma",
    "Instrumento de parceria",
    "Fluxo Processual",
    "Eventos",
    "Outro",
]


def _serialize_detail(project: Project) -> dict[str, Any]:
    """Monta o payload completo do Detalhe de Projeto.

    Reúne o projeto (card + campos editáveis), as etapas ordenadas (com contagem
    de tarefas read-only por etapa), os derivados read-only do projeto, as opções
    para os seletores de edição inline e as permissões de edição.

    Args:
        project: Instância de ``Project`` já validada para acesso.

    Returns:
        ``dict`` JSON-safe do detalhe.
    """
    # UX-only (autorização segue server-side por rota): leitor não deve ver
    # affordances de edição que responderiam 403 (F2-7).
    permissions = project_permission_flags(g.user, project)
    special_project_options = list(_SPECIAL_PROJECT_OPTIONS)
    if orgao_allows_inventario(project.orgao_ref.sigla if project.orgao_ref else None):
        special_project_options.append("Inventário")
    return {
        "project": serialize_project_detail(project),
        "etapas": project_etapas_payload(project, _connection_for_current_user()),
        "relacionados": listar_relacionados_payload(project, g.user),
        # Derivados read-only computados no backend (NÃO recalcular no cliente).
        "derived": {
            "data_inicio_projeto": (
                project.data_inicio_projeto.isoformat()
                if project.data_inicio_projeto
                else None
            ),
            "data_fim_projeto": (
                project.data_fim_projeto.isoformat()
                if project.data_fim_projeto
                else None
            ),
            "total_workflow_etapas": project.total_workflow_etapas,
            "todas_etapas_concluidas": project.todas_etapas_concluidas,
        },
        "options": {
            "status": _STATUS_OPTIONS,
            "prioridade": _PRIORIDADE_OPTIONS,
            "special_project": special_project_options,
            "delivery_type": _DELIVERY_TYPE_OPTIONS,
            "abep_indicator": ABEP_INDICADORES_OPTIONS,
            "orgaos": scoped_orgao_options(g.user),
        },
        "permissions": permissions,
    }


def _load_project_or_error(project_id: int) -> tuple[Project | None, Any]:
    """Carrega o projeto validando existência e rank de leitura.

    Returns:
        ``(project, None)`` quando autorizado; ``(None, fail_response)`` com o
        404 canônico (inexistente OU rank 0 — corpos idênticos, S5/F4-2b) caso
        contrário.
    """
    project = db.session.get(Project, project_id)
    denied = require_project_rank(project, PAPEL_LEITOR)
    if denied:
        return None, denied
    return project, None


@main_bp.route("/api/projetos/<int:project_id>/detalhe", methods=["GET"])
@api_login_required
def api_projeto_detalhe(project_id: int) -> Response | tuple[Response, int]:
    """Retorna o payload completo do Detalhe de Projeto no envelope canônico.

    Valida o acesso via ``require_project_rank`` (404 para inexistente e para
    rank 0). As tarefas de cada etapa entram SOMENTE como contagem (Fase 5a);
    a mutação fica para a Fase 5b.

    Args:
        project_id: ID do projeto.

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` (200); ou 404 canônico.
        401 JSON quando não há sessão (``api_login_required``).
    """
    project, error = _load_project_or_error(project_id)
    if error is not None:
        return error
    return ok(_serialize_detail(project))


@main_bp.route("/api/projetos/<int:project_id>/inline", methods=["POST"])
@api_login_required
def api_projeto_inline(project_id: int) -> Response | tuple[Response, int]:
    """Edita campos do projeto inline, reusando a lógica da rota Jinja.

    Reusa ``apply_project_inline_changes`` (mesma validação/normalização de
    ``update_project_inline``) e registra o histórico de igual forma. Diferente
    do fluxo Jinja (jsonify ``success``/status), responde no envelope canônico:
    erros de validação => 422 (``validation``); órgão sem permissão => 403
    (``forbidden``). Devolve o projeto atualizado (campos do detalhe).

    Args:
        project_id: ID do projeto.

    Returns:
        Envelope ``{"ok": true, "data": {"project": {...}, "changed": [...]}}``
        (200); 404 de acesso (rank 0); 422 (validation) ou 403 (forbidden, rank
        leitor) de validação; 401 JSON quando não há sessão.
    """
    project, error = _load_project_or_error(project_id)
    if error is not None:
        return error

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    previous_status = project.status
    try:
        changes = apply_project_inline_changes(project, data)
        if changes:
            if previous_status == "Finalizado" and project.status == "Vigente":
                log_project_action(
                    project_id=project.id,
                    action_type="reactivate",
                    description='Reabriu o projeto (status de "Finalizado" para "Vigente")',
                )
            else:
                change_desc = ", ".join(changes)
                log_project_action(
                    project_id=project.id,
                    action_type="edit",
                    description=f"Editou o projeto (inline): alterou {change_desc}",
                )
        db.session.commit()
    except ProjectInlineError as exc:
        db.session.rollback()
        if exc.status == 403:
            return fail(exc.message, status=403, code="forbidden")
        return fail(exc.message, status=422, code="validation")
    except Exception:
        db.session.rollback()
        return fail("Erro ao atualizar projeto.", status=422, code="validation")

    return ok({"project": serialize_project_detail(project), "changed": changes})


@main_bp.route("/api/projetos/<int:project_id>/tarefas-etapa", methods=["GET"])
@api_login_required
def api_projeto_tarefas_etapa(project_id: int) -> Response | tuple[Response, int]:
    """Lista SOMENTE LEITURA das tarefas de uma etapa do projeto.

    Reusa a mesma query de ``routes/projects/stage_tasks.py`` (tarefas não
    arquivadas da etapa, ordenadas), sem mutação. A criação/edição/mover de
    tarefas fica para a Fase 5b (Kanban + Drawer).

    Query params:
        ``etapa_id`` (obrigatório): ID da etapa cujas tarefas serão listadas.

    Returns:
        Envelope ``{"ok": true, "data": {"etapa_id", "tasks": [...]}}`` (200);
        404 (projeto inexistente ou invisível) / 422 (``etapa_id``
        ausente/inválido); 401 JSON sem sessão.
    """
    project, error = _load_project_or_error(project_id)
    if error is not None:
        return error

    etapa_id = request.args.get("etapa_id", type=int)
    if etapa_id is None:
        return fail("Parâmetro 'etapa_id' obrigatório.", status=422, code="validation")

    tasks = (
        Task.query.filter(
            Task.project_id == project.id,
            Task.etapa_id == etapa_id,
            Task.is_archived.is_(False),
        )
        .order_by(Task.ordem.asc(), Task.created_at.asc(), Task.id.asc())
        .all()
    )
    return ok(
        {
            "etapa_id": etapa_id,
            "tasks": [serialize_task_card(task) for task in tasks],
        }
    )
