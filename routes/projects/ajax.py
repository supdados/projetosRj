"""Lógica pura de edição inline de projeto, compartilhada com a API da SPA.

As rotas Jinja AJAX (``get_project_edit_data``/``update_project_inline``) foram
cortadas na migração — restam ``ProjectInlineError`` e
``apply_project_inline_changes``, importados por ``routes/api/project_detail.py``
(``POST /api/projetos/<id>/inline``).
"""

from flask import g

from catalogs.abep import normalize_abep_indicator
from catalogs.inventario import sanitize_special_project_for_orgao
from models import IndicadorProjeto, OrgaoUnidade, db
from catalogs.objectives import normalize_goal_selection

from routes.orgao_scope import get_user_orgao_subtree_ids


class ProjectInlineError(Exception):
    """Erro de validação na edição inline de um projeto.

    Carrega a ``message`` legível e o ``status`` HTTP que a rota deve devolver
    (400 para entrada inválida, 403 quando o usuário não pode mover o projeto
    para o órgão alvo). Permite que ``apply_project_inline_changes`` sinalize
    falhas de validação sem acoplar-se ao formato de resposta (Jinja jsonify vs.
    envelope canônico da API SPA).
    """

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def apply_project_inline_changes(project_to_edit, data):
    """Aplica os campos editáveis inline a um projeto (sem ``commit``).

    Fonte de verdade ÚNICA da edição inline: validações, normalização (ABEP,
    objetivos/indicadores) e a montagem da descrição legível das mudanças. NÃO
    faz ``commit`` nem registra histórico — isso fica a cargo do chamador, para
    que tanto a rota Jinja (``update_project_inline``) quanto o endpoint JSON da
    SPA (``/api/projetos/<id>/inline``) compartilhem exatamente a mesma lógica.

    Args:
        project_to_edit: Instância de ``Project`` a ser mutada.
        data: ``dict`` com os campos a atualizar (subconjunto dos campos do
            formulário inline).

    Returns:
        Lista de strings descrevendo cada mudança aplicada (para o histórico).

    Raises:
        ProjectInlineError: Quando um campo é inválido (órgão inexistente/
            inativo) ou o usuário não pode mover o projeto para o órgão alvo.
    """
    project_id = project_to_edit.id
    changes = []

    if "titulo" in data and data["titulo"] != project_to_edit.titulo:
        changes.append(f'título de "{project_to_edit.titulo}" para "{data["titulo"]}"')
        project_to_edit.titulo = data["titulo"]

    if "status" in data and data["status"] != project_to_edit.status:
        changes.append(f'status de "{project_to_edit.status}" para "{data["status"]}"')
        project_to_edit.status = data["status"]

    if "prioridade" in data and data["prioridade"] != project_to_edit.prioridade:
        changes.append(
            f'prioridade de "{project_to_edit.prioridade}" para "{data["prioridade"]}"'
        )
        project_to_edit.prioridade = data["prioridade"]

    if "orgao" in data:
        old_orgao = project_to_edit.orgao or ""
        new_orgao = data["orgao"] or ""
        if old_orgao != new_orgao:
            changes.append(
                f'órgão de "{old_orgao or "vazio"}" para "{new_orgao or "vazio"}"'
            )
        project_to_edit.orgao = data["orgao"] or None

    if "orgao_id" in data and data["orgao_id"] not in (None, "", "None"):
        try:
            new_orgao_id = int(data["orgao_id"])
        except (TypeError, ValueError):
            raise ProjectInlineError("Órgão inválido.", status=400)
        new_orgao_obj = db.session.get(OrgaoUnidade, new_orgao_id)
        if new_orgao_obj is None:
            raise ProjectInlineError("Órgão não encontrado.", status=400)
        if not new_orgao_obj.ativo and new_orgao_id != project_to_edit.orgao_id:
            raise ProjectInlineError(
                "Este órgão está inativo e não pode receber novos projetos.",
                status=400,
            )
        if not g.user.is_admin and new_orgao_id not in get_user_orgao_subtree_ids(
            g.user
        ):
            raise ProjectInlineError(
                "Você não tem permissão para mover o projeto para este órgão.",
                status=403,
            )
        if project_to_edit.orgao_id != new_orgao_id:
            old_sigla = (
                project_to_edit.orgao_ref.sigla
                if project_to_edit.orgao_ref
                else "vazio"
            )
            changes.append(
                f'órgão responsável de "{old_sigla}" para "{new_orgao_obj.sigla}"'
            )
            project_to_edit.orgao_id = new_orgao_id
            project_to_edit.special_project = sanitize_special_project_for_orgao(
                project_to_edit.special_project, new_orgao_obj.sigla
            )

    # Novos campos
    if "special_project" in data:
        current_orgao = db.session.get(OrgaoUnidade, project_to_edit.orgao_id)
        project_to_edit.special_project = sanitize_special_project_for_orgao(
            data["special_project"] or None,
            current_orgao.sigla if current_orgao else None,
        )

    if "sei_process" in data:
        project_to_edit.sei_process = data["sei_process"] or None

    if "short_description" in data:
        project_to_edit.short_description = data["short_description"] or None

    if "delivery_type" in data:
        project_to_edit.delivery_type = data["delivery_type"] or None

    if "abep_indicator" in data:
        old_abep = project_to_edit.abep_indicator
        new_abep = normalize_abep_indicator(data["abep_indicator"])
        if old_abep != new_abep:
            changes.append(
                f'indicador ABEP de "{old_abep or "vazio"}" para "{new_abep or "vazio"}"'
            )
        project_to_edit.abep_indicator = new_abep

    if "github_link" in data:
        project_to_edit.github_link = data["github_link"] or None

    if "documentation_link" in data:
        project_to_edit.documentation_link = data["documentation_link"] or None

    if "product_link" in data:
        project_to_edit.product_link = data["product_link"] or None

    if "observacao" in data:
        project_to_edit.observacao = data["observacao"] or None

    # Objetivo, Resultado e Indicadores
    goal_fields_present = any(
        field in data
        for field in ("objetivo_id", "resultado_esperado_id", "indicadores_ids")
    )
    if goal_fields_present:
        objetivo_raw = data.get("objetivo_id", project_to_edit.objetivo_id)
        resultado_raw = data.get(
            "resultado_esperado_id", project_to_edit.resultado_esperado_id
        )
        indicadores_raw = data.get(
            "indicadores_ids",
            [ip.indicador_id for ip in project_to_edit.indicadores],
        )

        objetivo_norm, resultado_norm, indicadores_norm = normalize_goal_selection(
            objetivo_raw,
            resultado_raw,
            indicadores_raw,
        )

        project_to_edit.objetivo_id = objetivo_norm
        project_to_edit.resultado_esperado_id = resultado_norm

        # Atualizar indicadores
        IndicadorProjeto.query.filter_by(project_id=project_id).delete()
        for indicador_id in indicadores_norm:
            indicador_projeto_novo = IndicadorProjeto(
                project_id=project_id,
                indicador_id=indicador_id,
            )
            db.session.add(indicador_projeto_novo)

    return changes
