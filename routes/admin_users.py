from flask import flash, g, redirect, render_template, request, url_for

from models import OrgaoUnidade, User, db
from services.govbr_oidc import normalize_cpf

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .orgao_tree import compute_orgao_depth
from .shared import get_or_404


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


@main_bp.route("/admin/users")
@login_required
@admin_required
def list_users():
    page = request.args.get("page", 1, type=int)
    # Ordenar por nome ou ID, por exemplo
    users_pagination = User.query.order_by(User.name).paginate(page=page, per_page=10)
    return render_template("admin/list_users.html", users=users_pagination)


@main_bp.route("/admin/users/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    if request.method == "POST":
        selected_orgao_ids, invalid_orgaos = _parse_selected_orgaos(
            request.form.getlist("orgaos_responsavel")
        )
        username = request.form.get("username")
        name = request.form.get("name")
        password = request.form.get("password")
        orgao = request.form.get("orgao")
        is_admin_form = request.form.get("is_admin") == "on"
        cpf_govbr, cpf_error = _parse_cpf_govbr(request.form.get("cpf_govbr"))

        if not username or not name or not password:
            flash("Username, Nome Completo e Senha são obrigatórios.", "danger")
        elif cpf_error:
            flash(f"CPF gov.br inválido: {cpf_error}", "danger")
        elif invalid_orgaos:
            flash(
                f'Órgão(s) inválido(s): {", ".join(invalid_orgaos)}. Atualize o formulário e tente novamente.',
                "danger",
            )
        elif User.query.filter_by(username=username).first():
            flash("Este nome de usuário já está em uso. Escolha outro.", "danger")
        elif cpf_govbr and User.query.filter_by(cpf_govbr=cpf_govbr).first():
            flash("Já existe um usuário vinculado a este CPF gov.br.", "danger")
        else:
            new_user = User(
                username=username,
                name=name,
                orgao=orgao if orgao else None,
                is_admin=is_admin_form,
                cpf_govbr=cpf_govbr,
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            new_user.set_orgaos(selected_orgao_ids)

            db.session.commit()
            flash(f'Usuário "{name}" ({username}) criado com sucesso!', "success")
            return redirect(url_for("main.list_users"))
        return render_template(
            "admin/user_form.html",
            user=request.form,
            user_orgao_ids=selected_orgao_ids,
            orgaos_with_depth=_list_orgaos_with_depth(),
            action_verb="Adicionar",
        )

    # Método GET: exibe o formulário para adicionar novo usuário
    return render_template(
        "admin/user_form.html",
        user=User(),
        user_orgao_ids=[],
        orgaos_with_depth=_list_orgaos_with_depth(),
        action_verb="Adicionar",
    )


@main_bp.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = get_or_404(User, user_id)
    hide_govbr_link_fields = bool(user_to_edit.cpf_govbr and user_to_edit.govbr_sub)
    if request.method == "POST":
        # Username geralmente não é editável ou requer cuidados especiais de unicidade
        user_to_edit.name = request.form.get("name")
        user_to_edit.orgao = (
            request.form.get("orgao") if request.form.get("orgao") else None
        )
        # Sentinel explícito (`orgaos_responsavel_submitted=1`) para detectar
        # que o form foi submetido mesmo quando o admin desmarcou todos os
        # checkboxes — caso em que `orgaos_responsavel` some do payload.
        orgaos_form_submitted = (
            "orgaos_responsavel_submitted" in request.form
            or "orgaos_responsavel" in request.form
        )
        current_orgao_ids = [uo.orgao_id for uo in user_to_edit.orgaos]
        invalid_orgaos = []
        if orgaos_form_submitted:
            selected_orgao_ids, invalid_orgaos = _parse_selected_orgaos(
                request.form.getlist("orgaos_responsavel")
            )
        else:
            selected_orgao_ids = current_orgao_ids
        should_update_cpf = not hide_govbr_link_fields and "cpf_govbr" in request.form
        cpf_govbr = user_to_edit.cpf_govbr
        cpf_error = None
        if should_update_cpf:
            cpf_govbr, cpf_error = _parse_cpf_govbr(request.form.get("cpf_govbr"))

        is_admin_form_val = request.form.get("is_admin") == "on"

        def _render_edit_form():
            return render_template(
                "admin/user_form.html",
                user=user_to_edit,
                user_orgao_ids=selected_orgao_ids,
                orgaos_with_depth=_list_orgaos_with_depth(),
                action_verb="Editar",
                hide_govbr_link_fields=hide_govbr_link_fields,
            )

        # Lógica para impedir que o último admin se despromova
        if user_to_edit.is_admin and not is_admin_form_val:
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                flash(
                    "Não é possível remover o status de administrador do único administrador existente.",
                    "danger",
                )
                return _render_edit_form()

        if invalid_orgaos:
            flash(
                f'Órgão(s) inválido(s): {", ".join(invalid_orgaos)}. Atualize o formulário e tente novamente.',
                "danger",
            )
            return _render_edit_form()

        if cpf_error:
            flash(f"CPF gov.br inválido: {cpf_error}", "danger")
            return _render_edit_form()

        if (
            should_update_cpf
            and cpf_govbr
            and User.query.filter(
                User.cpf_govbr == cpf_govbr, User.id != user_to_edit.id
            ).first()
        ):
            flash("Já existe um usuário vinculado a este CPF gov.br.", "danger")
            return _render_edit_form()

        user_to_edit.is_admin = is_admin_form_val
        if should_update_cpf:
            old_cpf = user_to_edit.cpf_govbr
            user_to_edit.cpf_govbr = cpf_govbr
            if not cpf_govbr or (old_cpf and old_cpf != cpf_govbr):
                user_to_edit.govbr_sub = None

        if orgaos_form_submitted:
            user_to_edit.set_orgaos(selected_orgao_ids)

        new_password = request.form.get("password")
        if new_password:  # Só atualiza a senha se uma nova for fornecida
            user_to_edit.set_password(new_password)

        db.session.commit()
        flash(f'Usuário "{user_to_edit.name}" atualizado com sucesso!', "success")
        return redirect(url_for("main.list_users"))

    # Método GET
    return render_template(
        "admin/user_form.html",
        user=user_to_edit,
        user_orgao_ids=[uo.orgao_id for uo in user_to_edit.orgaos],
        orgaos_with_depth=_list_orgaos_with_depth(),
        action_verb="Editar",
        hide_govbr_link_fields=hide_govbr_link_fields,
    )


@main_bp.route("/admin/users/remove-cpf/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def remove_cpf(user_id):
    user_to_edit = get_or_404(User, user_id)
    user_to_edit.cpf_govbr = None
    user_to_edit.govbr_sub = None
    db.session.commit()
    flash(
        f'CPF e vínculo gov.br do usuário "{user_to_edit.name}" foram removidos.',
        "success",
    )
    return redirect(url_for("main.edit_user", user_id=user_id))


@main_bp.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user_to_delete = get_or_404(User, user_id)

    if user_to_delete.id == g.user.id:  # Admin não pode se auto-excluir
        flash("Você não pode excluir sua própria conta de administrador.", "danger")
        return redirect(url_for("main.list_users"))

    if user_to_delete.is_admin and User.query.filter_by(is_admin=True).count() == 1:
        flash("Não é possível excluir o único administrador do sistema.", "danger")
        return redirect(url_for("main.list_users"))

    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f"Usuário {user_to_delete.username} excluído com sucesso.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir o usuário: {str(e)}", "danger")

    return redirect(url_for("main.list_users"))
