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

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    session['govbr_auth_state'] = state
    session['govbr_auth_nonce'] = nonce
    if next_page:
        session['govbr_auth_next'] = next_page
    else:
        session.pop('govbr_auth_next', None)

    try:
        auth_url = build_authorization_url(current_app.config, state=state, nonce=nonce)
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
    next_page = _resolve_safe_next_url(session.pop('govbr_auth_next', None))

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
        tokens = exchange_code_for_tokens(current_app.config, code=code)
        access_token = tokens.get('access_token')
        id_token = tokens.get('id_token')
        if not access_token or not id_token:
            raise GovBrOIDCError('Resposta de token incompleta.')

        id_payload = decode_jwt_payload(id_token)
        token_nonce = id_payload.get('nonce')
        # Alguns provedores RHSSO podem não incluir nonce no id_token em code flow.
        if expected_nonce and token_nonce and token_nonce != expected_nonce:
            raise GovBrOIDCError('Nonce do ID token não confere com a requisição original.')

        userinfo = fetch_userinfo(current_app.config, access_token=access_token)
    except GovBrOIDCError as exc:
        flash(f'Falha no login gov.br: {exc}', 'danger')
        return redirect(url_for('main.login_page'))

    cpf_value = userinfo.get('preferred_username') or id_payload.get('preferred_username')
    sub_value = userinfo.get('sub') or id_payload.get('sub')

    try:
        cpf = normalize_cpf(cpf_value)
    except ValueError:
        cpf = None

    if not cpf or not sub_value:
        flash('Não foi possível identificar o usuário gov.br (CPF/sub ausente).', 'danger')
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
        if matched_by_username and not user.cpf_govbr:
            user.cpf_govbr = cpf
            changed = True
        if not user.govbr_sub:
            user.govbr_sub = sub_value
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
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')

        if not current_password or not new_password or not confirm_new_password:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('change_password.html')

        if not g.user.check_password(current_password):
            flash('Senha atual incorreta.', 'danger')
            return render_template('change_password.html')

        if new_password != confirm_new_password:
            flash('A nova senha e a confirmação não correspondem.', 'danger')
            return render_template('change_password.html')
        
        if len(new_password) < 6:
            flash('A nova senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('change_password.html')

        g.user.set_password(new_password)
        db.session.commit()
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('change_password.html')
