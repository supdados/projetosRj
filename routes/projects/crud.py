from datetime import datetime

from flask import (
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    request,
    url_for,
)

from catalogs.abep import normalize_abep_indicator
from models import (
    OrgaoUnidade,
    Project,
    db,
)
from catalogs.objectives import normalize_goal_selection
from services.project_completion import ProjectCompletionError, complete_project
from services.project_creation import (
    ProjectCreationInput,
    StageDraft,
    create_project_record,
)

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.orgao_scope import get_user_orgao_subtree_ids, user_can_access_project
from routes.shared import (
    get_or_404,
    log_project_action,
)


def _resolve_orgao_from_form(form_value, *, current_orgao_id=None):
    """Parseia project_orgao_id do form e valida contra o subtree do usuario.

    Retorna ``(orgao_unidade, erro_msg)`` - um deles sempre None.
    - Admin pode escolher qualquer orgao ativo; nao-admin so dentro do seu subtree.
    - Orgaos inativos são rejeitados — exceto quando ``current_orgao_id`` aponta para
      eles (caso de edição de projeto legado vinculado a orgao desligado): nesse
      cenário preservamos o vínculo se o admin não mexeu no campo.
    """
    if not form_value:
        return None, "Você deve selecionar um órgão para o projeto."
    try:
        orgao_id = int(form_value)
    except (TypeError, ValueError):
        return None, "Órgão inválido."
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return None, "Órgão não encontrado."
    if not g.user.is_admin:
        if orgao_id not in get_user_orgao_subtree_ids(g.user):
            return (
                None,
                "Você não tem permissão para criar/editar projetos neste órgão.",
            )
    if not orgao.ativo and orgao_id != current_orgao_id:
        return None, "Este órgão está inativo e não pode receber novos projetos."
    return orgao, None


def _build_project_creation_input_from_form(orgao_unidade):
    """Monta ``ProjectCreationInput`` a partir de ``request.form`` (fonte Jinja).

    Centraliza o parsing do form de criação para que ``add_project`` (Jinja) e o
    chamador da API compartilhem a MESMA normalização de objetivos/ABEP/etapas.
    """
    objetivo_id, resultado_esperado_id, indicador_ids = normalize_goal_selection(
        request.form.get("project_objetivo"),
        request.form.get("project_resultado"),
        request.form.getlist("project_indicadores"),
    )

    project_start_date = request.form.get("project_start_date")
    start_date = None
    if project_start_date:
        try:
            start_date = datetime.strptime(project_start_date, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            current_app.logger.warning(
                "add_project: project_start_date inválido (recebido=%r, formato esperado=%%Y-%%m-%%d)",
                project_start_date,
            )

    etapa_descricoes = request.form.getlist("etapa_descricao")
    etapa_durations = request.form.getlist("etapa_duration")
    etapas = []
    for i, descricao in enumerate(etapa_descricoes):
        duration = None
        if i < len(etapa_durations) and etapa_durations[i]:
            try:
                duration = int(etapa_durations[i])
            except (TypeError, ValueError):
                current_app.logger.warning(
                    "add_project: etapa_duration inválido (recebido=%r, esperado int de dias)",
                    etapa_durations[i],
                )
        etapas.append(StageDraft(descricao=descricao, duration_days=duration))

    template_id_raw = request.form.get("project_template_id")
    template_id = None
    if template_id_raw:
        try:
            template_id = int(template_id_raw)
        except (TypeError, ValueError):
            template_id = None

    return ProjectCreationInput(
        titulo=request.form.get("project_titulo"),
        orgao_unidade=orgao_unidade,
        orgao=request.form.get("project_orgao"),
        prioridade=request.form.get("project_prioridade"),
        objetivo_id=objetivo_id,
        resultado_esperado_id=resultado_esperado_id,
        indicador_ids=indicador_ids,
        observacao=request.form.get("project_observacao"),
        special_project=request.form.get("project_special_project") or None,
        sei_process=request.form.get("project_sei_process") or None,
        short_description=request.form.get("project_short_description") or None,
        delivery_type=request.form.get("project_delivery_type") or None,
        abep_indicator=normalize_abep_indicator(
            request.form.get("project_abep_indicator")
        ),
        github_link=request.form.get("project_github_link") or None,
        documentation_link=request.form.get("project_documentation_link") or None,
        product_link=request.form.get("project_product_link") or None,
        etapas=etapas,
        start_date=start_date,
        template_id=template_id,
    )


@main_bp.route("/add_project", methods=["POST"])
@login_required
def add_project():
    try:
        titulo = request.form.get("project_titulo")
        if not titulo:
            flash("O título do projeto é obrigatório.", "danger")
            # Redirecionar para o painel pode ser uma boa opção de fallback
            return redirect(request.referrer or url_for("main.dashboard"))

        orgao_unidade, orgao_error = _resolve_orgao_from_form(
            request.form.get("project_orgao_id")
        )
        if orgao_error:
            flash(orgao_error, "danger")
            return redirect(request.referrer or url_for("main.dashboard"))

        creation_input = _build_project_creation_input_from_form(orgao_unidade)
        new_project = create_project_record(
            creation_input, created_by_id=g.user.id if g.user else None
        )

        # Registrar no histórico
        log_project_action(
            project_id=new_project.id,
            action_type="create",
            description=f'Criou o projeto "{titulo}"',
        )

        db.session.commit()

        flash("Projeto adicionado com sucesso!", "success")
        return redirect(url_for("main.project_detail", project_id=new_project.id))

    except ValueError as e:
        db.session.rollback()
        flash(str(e), "warning")
        return redirect(request.referrer or url_for("main.dashboard"))
    except Exception as e:
        db.session.rollback()
        flash(f"Ocorreu um erro ao adicionar o projeto: {e}", "danger")
        return redirect(request.referrer or url_for("main.dashboard"))


@main_bp.route("/project/<int:project_id>/delete", methods=["POST"])
@login_required
# @admin_required # Decida se apenas admin pode excluir. Se não, a lógica abaixo se aplica.
def delete_project(project_id):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    project_to_delete = get_or_404(Project, project_id)

    # Permissão para excluir: Admin pode excluir qualquer um.
    # Usuário não-admin só pode excluir projetos de suas áreas.
    if not user_can_access_project(g.user, project_to_delete):
        if is_ajax:
            from flask import jsonify

            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Você não tem permissão para excluir este projeto.",
                    }
                ),
                403,
            )
        flash("Você não tem permissão para excluir este projeto.", "danger")
        return redirect(url_for("main.list_projects"))

    # Registrar no histórico antes de excluir
    project_titulo = project_to_delete.titulo
    log_project_action(
        project_id=project_to_delete.id,
        action_type="delete",
        description=f'Excluiu o projeto "{project_titulo}"',
    )

    db.session.delete(project_to_delete)
    db.session.commit()

    if is_ajax:
        from flask import jsonify

        return jsonify({"ok": True, "message": f'Projeto "{project_titulo}" excluído.'})
    flash(f'Projeto "{project_titulo}" e suas etapas foram excluídos.', "success")
    return redirect(url_for("main.list_projects"))


@main_bp.route("/project/<int:project_id>/concluir", methods=["POST"])
@login_required
def concluir_project(project_id):
    project = get_or_404(Project, project_id)
    redirect_url = url_for("main.project_detail", project_id=project_id)
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

    def respond_error(message, category="warning", status_code=400):
        if is_ajax:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": message,
                        "category": category,
                        "redirect_url": redirect_url,
                    }
                ),
                status_code,
            )
        flash(message, category)
        return redirect(redirect_url)

    try:
        complete_project(project, g.user)
    except ProjectCompletionError as exc:
        return respond_error(exc.message, category=exc.category, status_code=exc.status)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Falha inesperada ao concluir projeto %s", project.id
        )
        return respond_error(
            "Erro ao concluir projeto. Tente novamente em instantes.",
            category="danger",
            status_code=500,
        )

    success_message = f'Projeto "{project.titulo}" foi concluído com sucesso!'
    if is_ajax:
        return jsonify(
            {"success": True, "message": success_message, "redirect_url": redirect_url}
        )
    flash(success_message, "success")
    return redirect(redirect_url)
