from flask import flash, g, redirect, render_template, request, url_for

from models import User, UserArea, db
from services.govbr_oidc import normalize_cpf

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .shared import get_area_catalog_choices, get_or_404, normalize_area_name


def _parse_selected_areas(raw_areas):
    area_catalog_choices = get_area_catalog_choices()
    catalog_map = {name.casefold(): name for name in area_catalog_choices}
    selected_areas = []
    invalid_areas = []
    seen = set()

    for raw_area in raw_areas:
        normalized = normalize_area_name(raw_area)
        if not normalized:
            continue
        key = normalized.casefold()
        canonical_name = catalog_map.get(key)
        if canonical_name is None:
            invalid_areas.append(normalized)
            continue
        if key in seen:
            continue
        seen.add(key)
        selected_areas.append(canonical_name)

    return selected_areas, invalid_areas, area_catalog_choices


def _parse_cpf_govbr(raw_cpf):
    if raw_cpf is None or not str(raw_cpf).strip():
        return None, None
    try:
        return normalize_cpf(raw_cpf), None
    except ValueError as exc:
        return None, str(exc)


def _normalize_selected_areas_for_form(selected_areas, area_catalog_choices):
    catalog_map = {
        normalize_area_name(area_name).casefold(): area_name
        for area_name in area_catalog_choices
        if normalize_area_name(area_name)
    }

    normalized_user_areas = []
    seen = set()

    for area in selected_areas:
        normalized_area = normalize_area_name(area)
        if not normalized_area:
            continue

        normalized_key = normalized_area.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)

        normalized_user_areas.append(catalog_map.get(normalized_key, normalized_area))

    return normalized_user_areas


def _area_choice_keys(selected_areas):
    keys = []
    seen = set()

    for area in selected_areas:
        normalized = normalize_area_name(area)
        if not normalized:
            continue

        key = normalized.casefold()
        if key in seen:
            continue

        seen.add(key)
        keys.append(key)

    return keys


@main_bp.route('/admin/users')
@login_required
@admin_required
def list_users():
    page = request.args.get('page', 1, type=int)
    # Ordenar por nome ou ID, por exemplo
    users_pagination = User.query.order_by(User.name).paginate(page=page, per_page=10)
    return render_template('admin/list_users.html', users=users_pagination)

@main_bp.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        selected_areas, invalid_areas, area_catalog_choices = _parse_selected_areas(
            request.form.getlist('areas_responsavel')
        )
        username = request.form.get('username')
        name = request.form.get('name')
        password = request.form.get('password')
        orgao = request.form.get('orgao')
        is_admin_form = request.form.get('is_admin') == 'on'
        cpf_govbr, cpf_error = _parse_cpf_govbr(request.form.get('cpf_govbr'))

        if not username or not name or not password:
            flash('Username, Nome Completo e Senha são obrigatórios.', 'danger')
        elif cpf_error:
            flash(f'CPF gov.br inválido: {cpf_error}', 'danger')
        elif invalid_areas:
            flash(
                f'Área(s) inválida(s): {", ".join(invalid_areas)}. Atualize o formulário e tente novamente.',
                'danger',
            )
        elif User.query.filter_by(username=username).first():
            flash('Este nome de usuário já está em uso. Escolha outro.', 'danger')
        elif cpf_govbr and User.query.filter_by(cpf_govbr=cpf_govbr).first():
            flash('Já existe um usuário vinculado a este CPF gov.br.', 'danger')
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
            db.session.flush()  # Para obter o ID do usuário
            
            # Adicionar áreas selecionadas
            for area in selected_areas:
                user_area = UserArea(user_id=new_user.id, area=area)
                db.session.add(user_area)
            
            db.session.commit()
            flash(f'Usuário "{name}" ({username}) criado com sucesso!', 'success')
            return redirect(url_for('main.list_users'))
        # Se caiu aqui, houve erro, então renderiza o form novamente com os dados (se o template suportar)
        # ou apenas renderiza o form vazio.
        return render_template(
            'admin/user_form.html',
            user=request.form,
            user_areas=selected_areas,
            user_area_keys=_area_choice_keys(selected_areas),
            action_verb="Adicionar",
            areas_responsaveis_choices=area_catalog_choices,
        )


    # Método GET: exibe o formulário para adicionar novo usuário
    return render_template(
        'admin/user_form.html',
        user=User(),
        user_areas=[],
        action_verb="Adicionar",
        areas_responsaveis_choices=get_area_catalog_choices(),
    )


@main_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = get_or_404(User, user_id)
    hide_govbr_link_fields = bool(user_to_edit.cpf_govbr and user_to_edit.govbr_sub)
    if request.method == 'POST':
        # Username geralmente não é editável ou requer cuidados especiais de unicidade
        user_to_edit.name = request.form.get('name')
        user_to_edit.orgao = request.form.get('orgao') if request.form.get('orgao') else None
        areas_form_submitted = 'areas_responsavel' in request.form
        selected_areas = user_to_edit.get_areas()
        invalid_areas = []
        area_catalog_choices = get_area_catalog_choices()
        normalized_selected_areas = _normalize_selected_areas_for_form(selected_areas, area_catalog_choices)

        if areas_form_submitted:
            selected_areas, invalid_areas, area_catalog_choices = _parse_selected_areas(
                request.form.getlist('areas_responsavel')
            )
            normalized_selected_areas = _normalize_selected_areas_for_form(
                selected_areas,
                area_catalog_choices,
            )
            selected_area_keys = _area_choice_keys(normalized_selected_areas)
        else:
            selected_area_keys = _area_choice_keys(normalized_selected_areas)
        should_update_cpf = not hide_govbr_link_fields and 'cpf_govbr' in request.form
        cpf_govbr = user_to_edit.cpf_govbr
        cpf_error = None
        if should_update_cpf:
            cpf_govbr, cpf_error = _parse_cpf_govbr(request.form.get('cpf_govbr'))
        
        is_admin_form_val = request.form.get('is_admin') == 'on'

        # Lógica para impedir que o último admin se despromova
        if user_to_edit.is_admin and not is_admin_form_val: # Tentando remover status de admin
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                flash('Não é possível remover o status de administrador do único administrador existente.', 'danger')
                # Não altera user_to_edit.is_admin e recarrega o form
                return render_template(
                    'admin/user_form.html',
                    user=user_to_edit,
                    user_areas=_normalize_selected_areas_for_form(
                        user_to_edit.get_areas(),
                        area_catalog_choices,
                    ),
                    user_area_keys=_area_choice_keys(
                        _normalize_selected_areas_for_form(
                            user_to_edit.get_areas(),
                            area_catalog_choices,
                        )
                    ),
                    action_verb="Editar",
                    areas_responsaveis_choices=area_catalog_choices,
                    hide_govbr_link_fields=hide_govbr_link_fields,
                )

        if invalid_areas:
            flash(
                f'Área(s) inválida(s): {", ".join(invalid_areas)}. Atualize o formulário e tente novamente.',
                'danger',
            )
            return render_template(
                'admin/user_form.html',
                user=user_to_edit,
                user_areas=normalized_selected_areas,
                user_area_keys=selected_area_keys,
                action_verb="Editar",
                areas_responsaveis_choices=area_catalog_choices,
                hide_govbr_link_fields=hide_govbr_link_fields,
            )

        if cpf_error:
            flash(f'CPF gov.br inválido: {cpf_error}', 'danger')
            return render_template(
                'admin/user_form.html',
                user=user_to_edit,
                user_areas=normalized_selected_areas,
                user_area_keys=selected_area_keys,
                action_verb="Editar",
                areas_responsaveis_choices=area_catalog_choices,
                hide_govbr_link_fields=hide_govbr_link_fields,
            )

        if (
            should_update_cpf
            and cpf_govbr
            and User.query.filter(User.cpf_govbr == cpf_govbr, User.id != user_to_edit.id).first()
        ):
            flash('Já existe um usuário vinculado a este CPF gov.br.', 'danger')
            return render_template(
                'admin/user_form.html',
                user=user_to_edit,
                user_areas=normalized_selected_areas,
                user_area_keys=selected_area_keys,
                action_verb="Editar",
                areas_responsaveis_choices=area_catalog_choices,
                hide_govbr_link_fields=hide_govbr_link_fields,
            )
        
        user_to_edit.is_admin = is_admin_form_val
        if should_update_cpf:
            old_cpf = user_to_edit.cpf_govbr
            user_to_edit.cpf_govbr = cpf_govbr
            if not cpf_govbr or (old_cpf and old_cpf != cpf_govbr):
                user_to_edit.govbr_sub = None

        if areas_form_submitted:
            # Atualizar áreas do usuário apenas quando o grupo de áreas foi submetido.
            # Caso o formulário venha sem a lista (por exemplo, em fluxo legado/compatibilidade),
            # mantém as áreas previamente cadastradas.
            user_to_edit.set_areas(selected_areas)

        new_password = request.form.get('password')
        if new_password: # Só atualiza a senha se uma nova for fornecida
            user_to_edit.set_password(new_password)
            
        db.session.commit()
        flash(f'Usuário "{user_to_edit.name}" atualizado com sucesso!', 'success')
        return redirect(url_for('main.list_users'))
    
    # Método GET
    area_catalog_choices = get_area_catalog_choices()
    selected_areas = _normalize_selected_areas_for_form(
        user_to_edit.get_areas(),
        area_catalog_choices,
    )
    return render_template(
        'admin/user_form.html',
        user=user_to_edit,
        user_areas=selected_areas,
        user_area_keys=_area_choice_keys(selected_areas),
        action_verb="Editar",
        areas_responsaveis_choices=area_catalog_choices,
        hide_govbr_link_fields=hide_govbr_link_fields,
    )

@main_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user_to_delete = get_or_404(User, user_id)

    if user_to_delete.id == g.user.id: # Admin não pode se auto-excluir
        flash('Você não pode excluir sua própria conta de administrador.', 'danger')
        return redirect(url_for('main.list_users'))

    if user_to_delete.is_admin and User.query.filter_by(is_admin=True).count() == 1:
        flash('Não é possível excluir o único administrador do sistema.', 'danger')
        return redirect(url_for('main.list_users'))
    
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'Usuário {user_to_delete.username} excluído com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir o usuário: {str(e)}', 'danger')

    return redirect(url_for('main.list_users'))
