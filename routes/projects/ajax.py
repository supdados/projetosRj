from flask import g, jsonify, request

from abep_catalog import normalize_abep_indicator
from models import IndicadorProjeto, Project, db
from objective_catalog import normalize_goal_selection

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.shared import (
    get_area_catalog_choices,
    is_area_in_catalog,
    resolve_catalog_area_name,
    get_or_404,
    get_goal_catalog_context,
    log_project_action,
)


@main_bp.route('/project/<int:project_id>/edit_data', methods=['GET'])
@login_required
def get_project_edit_data(project_id):
    """Endpoint AJAX para buscar dados necessários para edição"""
    project = get_or_404(Project, project_id)

    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para editar este projeto.'}), 403

    try:
        objetivos, resultados_por_objetivo, indicadores_por_resultado = get_goal_catalog_context()

        indicadores_do_projeto_ids = [ip.indicador_id for ip in project.indicadores]

        return jsonify({
            'success': True,
            'objetivos': objetivos,
            'resultados_por_objetivo': resultados_por_objetivo,
            'indicadores_por_resultado': indicadores_por_resultado,
            'indicadores_do_projeto': indicadores_do_projeto_ids,
            'areas_responsaveis': get_area_catalog_choices(),
            'is_admin': g.user.is_admin
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao buscar dados: {str(e)}'}), 500


@main_bp.route('/project/<int:project_id>/update_inline', methods=['POST'])
@login_required
def update_project_inline(project_id):
    """Endpoint AJAX para atualizar projeto inline"""
    project_to_edit = get_or_404(Project, project_id)

    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_edit.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para editar este projeto.'}), 403

    try:
        data = request.get_json()
        changes = []

        # Atualizar campos básicos
        if 'titulo' in data and data['titulo'] != project_to_edit.titulo:
            changes.append(f'título de "{project_to_edit.titulo}" para "{data["titulo"]}"')
            project_to_edit.titulo = data['titulo']

        if 'status' in data and data['status'] != project_to_edit.status:
            changes.append(f'status de "{project_to_edit.status}" para "{data["status"]}"')
            project_to_edit.status = data['status']

        if 'prioridade' in data and data['prioridade'] != project_to_edit.prioridade:
            changes.append(f'prioridade de "{project_to_edit.prioridade}" para "{data["prioridade"]}"')
            project_to_edit.prioridade = data['prioridade']

        if 'orgao' in data:
            old_orgao = project_to_edit.orgao or ""
            new_orgao = data['orgao'] or ""
            if old_orgao != new_orgao:
                changes.append(f'órgão de "{old_orgao or "vazio"}" para "{new_orgao or "vazio"}"')
            project_to_edit.orgao = data['orgao'] or None

        # Admin ou usuário com múltiplas áreas pode alterar área
        if 'area_responsavel' in data:
            new_area = data['area_responsavel']
            if new_area != project_to_edit.area_responsavel:
                if not is_area_in_catalog(new_area):
                    return jsonify({
                        'success': False,
                        'message': 'A área selecionada é inválida ou não está mais disponível.',
                    }), 400
                new_area = resolve_catalog_area_name(new_area)
                user_areas = g.user.get_areas()
                if g.user.is_admin or (len(user_areas) > 1 and new_area in user_areas):
                    changes.append(f'área de "{project_to_edit.area_responsavel}" para "{new_area}"')
                    project_to_edit.area_responsavel = new_area

        # Novos campos
        if 'special_project' in data:
            project_to_edit.special_project = data['special_project'] or None

        if 'sei_process' in data:
            project_to_edit.sei_process = data['sei_process'] or None

        if 'short_description' in data:
            project_to_edit.short_description = data['short_description'] or None

        if 'delivery_type' in data:
            project_to_edit.delivery_type = data['delivery_type'] or None

        if 'abep_indicator' in data:
            old_abep = project_to_edit.abep_indicator
            new_abep = normalize_abep_indicator(data['abep_indicator'])
            if old_abep != new_abep:
                changes.append(
                    f'indicador ABEP de "{old_abep or "vazio"}" para "{new_abep or "vazio"}"'
                )
            project_to_edit.abep_indicator = new_abep

        if 'github_link' in data:
            project_to_edit.github_link = data['github_link'] or None

        if 'documentation_link' in data:
            project_to_edit.documentation_link = data['documentation_link'] or None

        if 'observacao' in data:
            project_to_edit.observacao = data['observacao'] or None

        # Objetivo, Resultado e Indicadores
        goal_fields_present = any(
            field in data for field in ('objetivo_id', 'resultado_esperado_id', 'indicadores_ids')
        )
        if goal_fields_present:
            objetivo_raw = data.get('objetivo_id', project_to_edit.objetivo_id)
            resultado_raw = data.get('resultado_esperado_id', project_to_edit.resultado_esperado_id)
            indicadores_raw = data.get(
                'indicadores_ids',
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

        # Registrar no histórico
        if changes:
            change_desc = ', '.join(changes)
            log_project_action(
                project_id=project_id,
                action_type='edit',
                description=f'Editou o projeto (inline): alterou {change_desc}'
            )

        db.session.commit()
        return jsonify({'success': True, 'message': 'Projeto atualizado com sucesso!'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao atualizar projeto: {str(e)}'}), 500
