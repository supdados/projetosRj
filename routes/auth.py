import secrets
from urllib.parse import urlparse

from flask import current_app, flash, g, redirect, render_template, request, session, url_for

from models import User, db
from services.govbr_oidc import (
    GovBrOIDCError,
    build_authorization_url,
    build_logout_url,
    decode_jwt_payload,
    exchange_code_for_tokens,
    fetch_userinfo,
    format_cpf,
    is_govbr_oidc_enabled,
    normalize_cpf,
)

from .blueprint import main_bp
from .decorators import login_required


def _resolve_safe_next_url(raw_next):
    if not raw_next:
        return None

    value = str(raw_next).strip()
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        host = urlparse(request.host_url).netloc
        if parsed.scheme not in {"http", "https"}:
            return None
        if parsed.netloc != host:
            return None
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        return target if target.startswith("/") else None

    if not value.startswith("/") or value.startswith("//"):
        return None
    return value


def _find_user_by_cpf_for_govbr(cpf):
    user = User.query.filter_by(cpf_govbr=cpf).first()
    if user is not None:
        return user, False

    direct_candidates = {cpf, format_cpf(cpf)}
    user = User.query.filter(User.username.in_(direct_candidates)).first()
    if user is not None:
        return user, True

    for candidate in User.query.filter(User.username.isnot(None)).all():
        try:
            if normalize_cpf(candidate.username) == cpf:
                return candidate, True
        except ValueError:
            continue

    return None, False


def _login_redirect_target():
    next_page = _resolve_safe_next_url(request.form.get("next") or request.args.get("next"))
    return next_page or url_for("main.dashboard")


def _build_config_with_redirect_uri(redirect_uri):
    if not redirect_uri:
        return current_app.config
    config = dict(current_app.config)
    config["GOVBR_OIDC_REDIRECT_URI"] = redirect_uri
    return config


def _resolve_runtime_govbr_redirect_uri():
    configured_redirect_uri = str(current_app.config.get("GOVBR_OIDC_REDIRECT_URI", "")).strip()
    if not configured_redirect_uri:
        return None

    parsed = urlparse(configured_redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        return url_for("main.login_govbr_callback", _external=True)

    request_hostname = request.host.split(":", 1)[0]
    if parsed.scheme == request.scheme and parsed.hostname == request_hostname:
        return configured_redirect_uri

    return parsed._replace(scheme=request.scheme, netloc=request.host).geturl()


def _remember_auth_session(user, *, provider, id_token=None):
    session.clear()
    session["user_id"] = user.id
    session["auth_provider"] = provider
    if provider == "govbr" and id_token:
        session["govbr_id_token"] = id_token


@main_bp.route('/', methods=['GET'])
def home():
    if 'user_id' in session and g.user: # Se logado e usuário válido
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login_page'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if 'user_id' in session and g.user: # Se já logado e usuário válido
        return redirect(url_for('main.dashboard'))

    safe_next = _resolve_safe_next_url(request.args.get('next') or request.form.get('next'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Usuário e senha são obrigatórios.', 'warning')
            return render_template('login.html', next_page=safe_next)

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            _remember_auth_session(user, provider='local')
            g.user = user

            flash(f'Login bem-sucedido, {user.name}!', 'success')
            return redirect(_login_redirect_target())
        else:
            flash('Credenciais inválidas. Tente novamente.', 'danger')
            return render_template('login.html', next_page=safe_next)
    return render_template('login.html', next_page=safe_next)


@main_bp.route('/login/govbr', methods=['GET'])
def login_govbr():
    if 'user_id' in session and g.user:
        return redirect(url_for('main.dashboard'))

    next_page = _resolve_safe_next_url(request.args.get('next'))
    if not is_govbr_oidc_enabled(current_app.config):
        flash('Login gov.br indisponível no momento.', 'warning')
        if next_page:
            return redirect(url_for('main.login_page', next=next_page))
        return redirect(url_for('main.login_page'))

    runtime_redirect_uri = _resolve_runtime_govbr_redirect_uri()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    session['govbr_auth_state'] = state
    session['govbr_auth_nonce'] = nonce
    if runtime_redirect_uri:
        session['govbr_auth_redirect_uri'] = runtime_redirect_uri
    else:
        session.pop('govbr_auth_redirect_uri', None)
    if next_page:
        session['govbr_auth_next'] = next_page
    else:
        session.pop('govbr_auth_next', None)

    try:
        auth_url = build_authorization_url(
            _build_config_with_redirect_uri(runtime_redirect_uri),
            state=state,
            nonce=nonce,
        )
    except GovBrOIDCError as exc:
        flash(f'Falha ao iniciar login gov.br: {exc}', 'danger')
        return redirect(url_for('main.login_page'))

    return redirect(auth_url)


@main_bp.route('/auth/govbr/callback', methods=['GET'])
def login_govbr_callback():
    if not is_govbr_oidc_enabled(current_app.config):
        flash('Login gov.br indisponível no momento.', 'warning')
        return redirect(url_for('main.login_page'))

    expected_state = session.pop('govbr_auth_state', None)
    expected_nonce = session.pop('govbr_auth_nonce', None)
    auth_redirect_uri = session.pop('govbr_auth_redirect_uri', None)
    next_page = _resolve_safe_next_url(session.pop('govbr_auth_next', None))
    auth_config = _build_config_with_redirect_uri(auth_redirect_uri)

    provider_error = request.args.get('error')
    if provider_error:
        flash(f'Autenticação gov.br não concluída: {provider_error}.', 'danger')
        return redirect(url_for('main.login_page'))

    code = request.args.get('code')
    state = request.args.get('state')

    if not code or not state:
        flash('Resposta de autenticação gov.br inválida (code/state ausente).', 'danger')
        return redirect(url_for('main.login_page'))

    if not expected_state:
        flash(
            'Sessão de autenticação gov.br não encontrada. Inicie o login novamente na mesma URL da aplicação.',
            'danger',
        )
        return redirect(url_for('main.login_page'))

    if state != expected_state:
        flash('Resposta de autenticação gov.br inválida (state divergente).', 'danger')
        return redirect(url_for('main.login_page'))

    try:
        tokens = exchange_code_for_tokens(auth_config, code=code)
        access_token = tokens.get('access_token')
        id_token = tokens.get('id_token')
        if not access_token or not id_token:
            raise GovBrOIDCError('Resposta de token incompleta.')

        id_payload = decode_jwt_payload(id_token)
        token_nonce = id_payload.get('nonce')
        # Alguns provedores RHSSO podem não incluir nonce no id_token em code flow.
        if expected_nonce and token_nonce and token_nonce != expected_nonce:
            raise GovBrOIDCError('Nonce do ID token não confere com a requisição original.')

        userinfo = fetch_userinfo(auth_config, access_token=access_token)
    except GovBrOIDCError as exc:
        flash(f'Falha no login gov.br: {exc}', 'danger')
        return redirect(url_for('main.login_page'))

    cpf_value = userinfo.get('preferred_username') or id_payload.get('preferred_username')
    sub_value = userinfo.get('sub') or id_payload.get('sub')

    if not sub_value:
        flash('Não foi possível identificar o usuário gov.br (sub ausente).', 'danger')
        return redirect(url_for('main.login_page'))

    try:
        cpf = normalize_cpf(cpf_value) if cpf_value is not None else None
    except ValueError:
        cpf = None

    user = User.query.filter_by(govbr_sub=sub_value).first()
    matched_by_username = False
    is_first_link = user is None

    if is_first_link:
        if not cpf:
            flash(
                'Usuário gov.br não vinculado no sistema (CPF não retornado para vínculo inicial).',
                'danger',
            )
            return redirect(url_for('main.login_page'))

        user, matched_by_username = _find_user_by_cpf_for_govbr(cpf)
        if user is None:
            flash('Usuário gov.br não vinculado no sistema. Solicite cadastro de CPF ao administrador.', 'danger')
            return redirect(url_for('main.login_page'))

        if user.govbr_sub and user.govbr_sub != sub_value:
            flash('Vínculo gov.br inconsistente para este usuário. Contate o administrador.', 'danger')
            return redirect(url_for('main.login_page'))

    try:
        changed = False
        if is_first_link and matched_by_username and cpf and not user.cpf_govbr:
            user.cpf_govbr = cpf
            changed = True
        if is_first_link and not user.govbr_sub:
            user.govbr_sub = sub_value
            changed = True
        if not is_first_link and cpf and not user.cpf_govbr:
            # Backfill opcional de CPF para usuários já vinculados por sub.
            user.cpf_govbr = cpf
            changed = True
        if changed:
            db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Falha ao persistir vínculo gov.br do usuário.', 'danger')
        return redirect(url_for('main.login_page'))

    _remember_auth_session(user, provider='govbr', id_token=id_token)
    g.user = user
    flash(f'Login gov.br bem-sucedido, {user.name}!', 'success')
    return redirect(next_page or url_for('main.dashboard'))

@main_bp.route('/logout')
@login_required # Só pode fazer logout se estiver logado
def logout():
    logout_url = None
    if (
        current_app.config.get('GOVBR_OIDC_FEDERATED_LOGOUT_ENABLED')
        and session.get('auth_provider') == 'govbr'
        and session.get('govbr_id_token')
        and is_govbr_oidc_enabled(current_app.config)
    ):
        try:
            logout_url = build_logout_url(
                current_app.config,
                id_token_hint=session['govbr_id_token'],
                post_logout_redirect_uri=current_app.config.get('GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI'),
            )
        except GovBrOIDCError:
            logout_url = None

    session.clear()
    g.user = None # Limpa g.user também
    flash('Você foi desconectado.', 'info')
    if logout_url:
        return redirect(logout_url)
    return redirect(url_for('main.login_page'))

@main_bp.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    is_govbr_linked = bool(g.user and g.user.cpf_govbr and g.user.govbr_sub)

    if request.method == 'POST':
        submitted_name = request.form.get('name')
        name = (submitted_name if submitted_name is not None else g.user.name or '').strip()
        if not name:
            flash('O nome é obrigatório.', 'danger')
            return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)

        new_cpf = g.user.cpf_govbr
        if not is_govbr_linked and 'cpf_govbr' in request.form:
            raw_cpf = request.form.get('cpf_govbr')
            if raw_cpf is None or not str(raw_cpf).strip():
                new_cpf = None
            else:
                try:
                    new_cpf = normalize_cpf(raw_cpf)
                except ValueError as exc:
                    flash(f'CPF gov.br inválido: {exc}', 'danger')
                    return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)

            if (
                new_cpf
                and User.query.filter(User.cpf_govbr == new_cpf, User.id != g.user.id).first()
            ):
                flash('Já existe um usuário vinculado a este CPF gov.br.', 'danger')
                return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)

        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')

        should_update_password = bool(current_password or new_password or confirm_new_password)
        if should_update_password and (not current_password or not new_password or not confirm_new_password):
            flash('Para alterar a senha, preencha senha atual, nova senha e confirmação.', 'danger')
            return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)

        if should_update_password and not g.user.check_password(current_password):
            flash('Senha atual incorreta.', 'danger')
            return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)

        if should_update_password and new_password != confirm_new_password:
            flash('A nova senha e a confirmação não correspondem.', 'danger')
            return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)

        if should_update_password and len(new_password) < 6:
            flash('A nova senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)

        g.user.name = name
        if not is_govbr_linked and 'cpf_govbr' in request.form:
            g.user.cpf_govbr = new_cpf
        if should_update_password:
            g.user.set_password(new_password)
        db.session.commit()
        if should_update_password:
            flash('Conta atualizada e senha alterada com sucesso!', 'success')
        else:
            flash('Conta atualizada com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('change_password.html', hide_govbr_link_fields=is_govbr_linked)
