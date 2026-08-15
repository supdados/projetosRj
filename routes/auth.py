import secrets
import time
from datetime import timedelta
from urllib.parse import urlparse

from flask import (
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import OrgaoUnidade, Project, Task, User, db
from routes.safe_redirect import safe_internal_path
from time_utils import utc_now
from services.password_policy import validate_password_strength
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

from flask_limiter.util import get_remote_address

from extensions import limiter

from .blueprint import main_bp
from .decorators import login_required

LOCAL_LOGIN_MAX_ATTEMPTS = 5
LOCAL_LOGIN_LOCKOUT_MINUTES = 15
LOGIN_STATS_CACHE_KEY = "login_public_stats"


def _query_login_stats():
    count_vigente = Project.query.filter_by(status="Vigente").count()
    count_finalizado = Project.query.filter_by(status="Finalizado").count()
    total_tasks = Task.query.count()
    count_areas = OrgaoUnidade.query.filter_by(ativo=True).count()
    return count_vigente, count_finalizado, total_tasks, count_areas


def _login_stats():
    ttl_seconds = int(current_app.config.get("LOGIN_PUBLIC_STATS_CACHE_SECONDS", 300))
    if ttl_seconds <= 0:
        return _query_login_stats()

    cache = current_app.extensions.setdefault(LOGIN_STATS_CACHE_KEY, {})
    now = time.monotonic()
    cached_stats = cache.get("stats")
    if cached_stats is not None and cache.get("expires_at", 0) > now:
        return cached_stats

    stats = _query_login_stats()
    cache["stats"] = stats
    cache["expires_at"] = now + ttl_seconds
    return stats


def _user_is_locked_out(user):
    if not user or not user.lockout_until:
        return False
    return user.lockout_until > utc_now()


def _register_failed_login(user):
    if user is None:
        return
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    locked = False
    if user.failed_login_attempts >= LOCAL_LOGIN_MAX_ATTEMPTS:
        user.lockout_until = utc_now() + timedelta(minutes=LOCAL_LOGIN_LOCKOUT_MINUTES)
        user.failed_login_attempts = 0
        locked = True
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    if locked:
        _log_auth_event("account_locked", user=user, provider="local")


def _register_successful_login(user):
    if user is None:
        return
    dirty = False
    if user.failed_login_attempts:
        user.failed_login_attempts = 0
        dirty = True
    if user.lockout_until is not None:
        user.lockout_until = None
        dirty = True
    if dirty:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def _log_auth_event(event, *, user=None, username=None, provider="local"):
    """Registra um evento de autenticação para auditoria (OWASP A09).

    Loga em formato estruturado (key=value) com identidade, provedor e IP de
    origem; nunca inclui senha nem token. ``event`` é um dos rótulos:
    ``login_success`` | ``login_failure`` | ``account_locked`` | ``logout`` |
    ``password_changed``.

    Exemplo:
        >>> _log_auth_event("login_success", user=user, provider="govbr")
    """
    current_app.logger.info(
        "auth_event event=%s provider=%s user_id=%s username=%s ip=%s",
        event,
        provider,
        getattr(user, "id", None),
        username if username is not None else getattr(user, "username", None),
        request.remote_addr,
    )


def _resolve_safe_next_url(raw_next):
    return safe_internal_path(raw_next, request.host)


def _find_user_by_cpf_for_govbr(cpf):
    user = User.query.filter_by(cpf_govbr=cpf).first()
    if user is not None:
        return user, False

    direct_candidates = {cpf, format_cpf(cpf)}
    user = User.query.filter(User.username.in_(direct_candidates)).first()
    if user is not None:
        return user, True

    # O scan O(n) por username normalizado saiu: scripts/migrations/backfill_cpf_govbr.py
    # populou a coluna indexada acima (e o backfill on-demand cobre vínculos novos).
    return None, False


def _login_redirect_target():
    next_page = _resolve_safe_next_url(
        request.form.get("next") or request.args.get("next")
    )
    return next_page or url_for("main.dashboard")


def _build_config_with_redirect_uri(redirect_uri):
    if not redirect_uri:
        return current_app.config
    config = dict(current_app.config)
    config["GOVBR_OIDC_REDIRECT_URI"] = redirect_uri
    return config


def _derive_govbr_redirect_uri_from_request() -> str | None:
    """Deriva o redirect_uri do host/scheme do request (comportamento legado).

    Só existe como fallback de transição para ambientes sem
    ``GOVBR_OIDC_REDIRECT_URI_FIXED``; atrás de proxy o Host visto aqui é o
    interno, por isso o alvo é a config explícita + ProxyFix.
    """
    configured_redirect_uri = str(
        current_app.config.get("GOVBR_OIDC_REDIRECT_URI", "")
    ).strip()
    if not configured_redirect_uri:
        return None

    parsed = urlparse(configured_redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        return url_for("main.login_govbr_callback", _external=True)

    request_hostname = request.host.split(":", 1)[0]
    if parsed.scheme == request.scheme and parsed.hostname == request_hostname:
        return configured_redirect_uri

    return parsed._replace(scheme=request.scheme, netloc=request.host).geturl()


def _resolve_runtime_govbr_redirect_uri() -> str | None:
    """redirect_uri enviado ao IdP no authorize e reapresentado no token.

    Config explícita por ambiente vence; sem ela, cai na derivação legada —
    o valor gerado nos cenários de hoje permanece idêntico.

    Ex.: com ``GOVBR_OIDC_REDIRECT_URI_FIXED=https://app.rj.gov.br/auth/govbr/callback``
    devolve essa string literal, qualquer que seja o Host do request.
    """
    fixed_redirect_uri = str(
        current_app.config.get("GOVBR_OIDC_REDIRECT_URI_FIXED", "")
    ).strip()
    if fixed_redirect_uri:
        return fixed_redirect_uri
    return _derive_govbr_redirect_uri_from_request()


def _remember_auth_session(user, *, provider, id_token=None):
    # Garante cookie de sessão novo após autenticar (mitigação de session fixation).
    session.clear()
    # session.clear() apaga o _permanent setado no before_request: sem isto o cookie sai sem Expires.
    session.permanent = True
    session["_sid_rotation"] = secrets.token_urlsafe(16)
    session["user_id"] = user.id
    session["auth_provider"] = provider
    session["login_at"] = time.time()
    if provider == "govbr" and id_token:
        session["govbr_id_token"] = id_token


@main_bp.route("/", methods=["GET"])
def home():
    if "user_id" in session and g.user:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.login_page"))


def _login_rate_key():
    """Chave de rate-limit por (IP + username): throttla brute-force contra UMA
    conta a partir de um IP sem afetar o login legítimo do dono (cujo IP é outro
    balde). Username normalizado para evitar bypass por variação de caixa."""
    username = (request.form.get("username") or "").strip().lower()
    return f"{get_remote_address()}|{username}"


def _render_login_page(safe_next, *, show_local_form=False):
    cv, cf, tt, ca = _login_stats()
    return render_template(
        "auth/login.html",
        next_page=safe_next,
        show_local_form=show_local_form,
        count_vigente=cv,
        count_finalizado=cf,
        total_tasks=tt,
        count_areas=ca,
    )


@main_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])  # geral, por IP (credential stuffing)
@limiter.limit("5 per minute", key_func=_login_rate_key, methods=["POST"])  # por conta
def login_page():
    if "user_id" in session and g.user:
        return redirect(url_for("main.dashboard"))

    safe_next = _resolve_safe_next_url(
        request.args.get("next") or request.form.get("next")
    )

    if request.method != "POST":
        return _render_login_page(safe_next)

    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not password:
        flash("Usuário e senha são obrigatórios.", "warning")
        return _render_login_page(safe_next, show_local_form=True)

    user = User.query.filter_by(username=username).first()

    # Durante o lockout, nega o login mesmo com a senha correta (CWE-307). Usa a
    # MESMA mensagem genérica do caminho de falha para não permitir enumeração de
    # usuários (conta bloqueada x inexistente respondem idêntico).
    if _user_is_locked_out(user):
        _log_auth_event("login_blocked", user=user, username=username, provider="local")
        flash("Credenciais inválidas. Tente novamente.", "danger")
        return _render_login_page(safe_next, show_local_form=True)

    if user and user.check_password(password):
        if user.needs_password_rehash():
            user.set_password(password)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        _register_successful_login(user)
        _remember_auth_session(user, provider="local")
        g.user = user

        _log_auth_event("login_success", user=user, provider="local")
        flash(f"Login bem-sucedido, {user.name}!", "success")
        return redirect(_login_redirect_target())

    _register_failed_login(user)
    _log_auth_event("login_failure", user=user, username=username, provider="local")
    flash("Credenciais inválidas. Tente novamente.", "danger")
    return _render_login_page(safe_next, show_local_form=True)


@main_bp.route("/login/govbr", methods=["GET"])
@limiter.limit("30 per minute")
def login_govbr():
    if "user_id" in session and g.user:
        return redirect(url_for("main.dashboard"))

    next_page = _resolve_safe_next_url(request.args.get("next"))
    if not is_govbr_oidc_enabled(current_app.config):
        flash("Login gov.br indisponível no momento.", "warning")
        if next_page:
            return redirect(url_for("main.login_page", next=next_page))
        return redirect(url_for("main.login_page"))

    runtime_redirect_uri = _resolve_runtime_govbr_redirect_uri()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    session["govbr_auth_state"] = state
    session["govbr_auth_nonce"] = nonce
    if runtime_redirect_uri:
        session["govbr_auth_redirect_uri"] = runtime_redirect_uri
    else:
        session.pop("govbr_auth_redirect_uri", None)
    if next_page:
        session["govbr_auth_next"] = next_page
    else:
        session.pop("govbr_auth_next", None)

    try:
        auth_url = build_authorization_url(
            _build_config_with_redirect_uri(runtime_redirect_uri),
            state=state,
            nonce=nonce,
        )
    except GovBrOIDCError as exc:
        flash(f"Falha ao iniciar login gov.br: {exc}", "danger")
        return redirect(url_for("main.login_page"))

    return redirect(auth_url)


@main_bp.route("/auth/govbr/callback", methods=["GET"])
@limiter.limit("30 per minute")
def login_govbr_callback():
    if not is_govbr_oidc_enabled(current_app.config):
        flash("Login gov.br indisponível no momento.", "warning")
        return redirect(url_for("main.login_page"))

    expected_state = session.pop("govbr_auth_state", None)
    expected_nonce = session.pop("govbr_auth_nonce", None)
    auth_redirect_uri = session.pop("govbr_auth_redirect_uri", None)
    next_page = _resolve_safe_next_url(session.pop("govbr_auth_next", None))
    auth_config = _build_config_with_redirect_uri(auth_redirect_uri)

    provider_error = request.args.get("error")
    if provider_error:
        flash(f"Autenticação gov.br não concluída: {provider_error}.", "danger")
        return redirect(url_for("main.login_page"))

    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state:
        flash(
            "Resposta de autenticação gov.br inválida (code/state ausente).", "danger"
        )
        return redirect(url_for("main.login_page"))

    if not expected_state:
        flash(
            "Sessão de autenticação gov.br não encontrada. Inicie o login novamente na mesma URL da aplicação.",
            "danger",
        )
        return redirect(url_for("main.login_page"))

    if state != expected_state:
        flash("Resposta de autenticação gov.br inválida (state divergente).", "danger")
        return redirect(url_for("main.login_page"))

    try:
        tokens = exchange_code_for_tokens(auth_config, code=code)
        access_token = tokens.get("access_token")
        id_token = tokens.get("id_token")
        if not access_token or not id_token:
            raise GovBrOIDCError("Resposta de token incompleta.")

        id_payload = decode_jwt_payload(id_token, config=auth_config)
        # Nonce enviado na authorize é obrigatório no id_token: ausência ou
        # divergência indica replay/injeção de token e derruba o login.
        if expected_nonce and id_payload.get("nonce") != expected_nonce:
            raise GovBrOIDCError(
                "Nonce do ID token ausente ou divergente da requisição original."
            )

        userinfo = fetch_userinfo(auth_config, access_token=access_token)
    except GovBrOIDCError as exc:
        current_app.logger.exception("Falha no login gov.br: %s", exc)
        flash(f"Falha no login gov.br: {exc}", "danger")
        return redirect(url_for("main.login_page"))

    cpf_value = userinfo.get("preferred_username") or id_payload.get(
        "preferred_username"
    )
    # Identidade primária vem SEMPRE do id_token verificado; userinfo apenas
    # complementa claims e nunca pode trocar o sub.
    sub_value = id_payload.get("sub")

    if not sub_value:
        flash("Não foi possível identificar o usuário gov.br (sub ausente).", "danger")
        return redirect(url_for("main.login_page"))

    userinfo_sub = userinfo.get("sub")
    if userinfo_sub is not None and userinfo_sub != sub_value:
        current_app.logger.error(
            "auth_event event=govbr_sub_mismatch id_token_sub=%s userinfo_sub=%s ip=%s",
            sub_value,
            userinfo_sub,
            request.remote_addr,
        )
        flash("Falha na validação da identidade gov.br.", "danger")
        return redirect(url_for("main.login_page"))

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
                "Usuário gov.br não vinculado no sistema (CPF não retornado para vínculo inicial).",
                "danger",
            )
            return redirect(url_for("main.login_page"))

        user, matched_by_username = _find_user_by_cpf_for_govbr(cpf)
        if user is None:
            flash(
                "Usuário gov.br não vinculado no sistema. Solicite cadastro de CPF ao administrador.",
                "danger",
            )
            return redirect(url_for("main.login_page"))

        if user.govbr_sub and user.govbr_sub != sub_value:
            flash(
                "Vínculo gov.br inconsistente para este usuário. Contate o administrador.",
                "danger",
            )
            return redirect(url_for("main.login_page"))

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
        flash("Falha ao persistir vínculo gov.br do usuário.", "danger")
        return redirect(url_for("main.login_page"))

    _remember_auth_session(user, provider="govbr", id_token=id_token)
    _log_auth_event("login_success", user=user, provider="govbr")
    g.user = user
    flash(f"Login gov.br bem-sucedido, {user.name}!", "success")
    # O access/refresh token Gov.br morre aqui: a identidade já veio do par
    # verificado e quem governa o login daqui em diante é a sessão Flask (8h).
    return redirect(next_page or url_for("main.dashboard"))


@main_bp.route("/logout")
@login_required
def logout():
    logout_url = None
    if (
        current_app.config.get("GOVBR_OIDC_FEDERATED_LOGOUT_ENABLED")
        and session.get("auth_provider") == "govbr"
        and session.get("govbr_id_token")
        and is_govbr_oidc_enabled(current_app.config)
    ):
        try:
            logout_url = build_logout_url(
                current_app.config,
                id_token_hint=session["govbr_id_token"],
                post_logout_redirect_uri=current_app.config.get(
                    "GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI"
                ),
            )
        except GovBrOIDCError:
            logout_url = None

    _log_auth_event(
        "logout", user=g.user, provider=session.get("auth_provider", "local")
    )
    session.clear()
    g.user = None
    flash("Você foi desconectado.", "info")
    response = redirect(logout_url or url_for("main.login_page"))
    # Higiene pós-sprint-6: navegadores logados antes do deploy ainda carregam o
    # cookie legado com refresh token do IdP; remover este delete após um ciclo.
    response.delete_cookie("govbr_refresh_token")
    return response


@main_bp.route("/profile/change-password", methods=["GET", "POST"])
@login_required
@limiter.limit("5 per minute", methods=["POST"])
def change_password():
    is_govbr_linked = bool(g.user and g.user.cpf_govbr and g.user.govbr_sub)

    if request.method == "POST":
        submitted_name = request.form.get("name")
        name = (
            submitted_name if submitted_name is not None else g.user.name or ""
        ).strip()
        if not name:
            flash("O nome é obrigatório.", "danger")
            return render_template(
                "auth/change_password.html", hide_govbr_link_fields=is_govbr_linked
            )

        if not is_govbr_linked and "cpf_govbr" in request.form:
            raw_cpf = request.form.get("cpf_govbr")
            if raw_cpf and str(raw_cpf).strip():
                try:
                    requested_cpf = normalize_cpf(raw_cpf)
                except ValueError as exc:
                    flash(f"CPF gov.br inválido: {exc}", "danger")
                    return render_template(
                        "auth/change_password.html",
                        hide_govbr_link_fields=is_govbr_linked,
                    )
                if requested_cpf != (g.user.cpf_govbr or ""):
                    flash(
                        "Alteração de CPF gov.br por autoatendimento está desativada. Solicite ao administrador.",
                        "danger",
                    )
                    return render_template(
                        "auth/change_password.html",
                        hide_govbr_link_fields=is_govbr_linked,
                    )

        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_new_password = request.form.get("confirm_new_password")

        should_update_password = bool(
            current_password or new_password or confirm_new_password
        )
        if should_update_password and (
            not current_password or not new_password or not confirm_new_password
        ):
            flash(
                "Para alterar a senha, preencha senha atual, nova senha e confirmação.",
                "danger",
            )
            return render_template(
                "auth/change_password.html", hide_govbr_link_fields=is_govbr_linked
            )

        if should_update_password and not g.user.check_password(current_password):
            flash("Senha atual incorreta.", "danger")
            return render_template(
                "auth/change_password.html", hide_govbr_link_fields=is_govbr_linked
            )

        if should_update_password and new_password != confirm_new_password:
            flash("A nova senha e a confirmação não correspondem.", "danger")
            return render_template(
                "auth/change_password.html", hide_govbr_link_fields=is_govbr_linked
            )

        password_error = (
            validate_password_strength(new_password) if should_update_password else None
        )
        if password_error:
            flash(password_error, "danger")
            return render_template(
                "auth/change_password.html", hide_govbr_link_fields=is_govbr_linked
            )

        g.user.name = name
        if should_update_password:
            g.user.set_password(new_password)
        db.session.commit()
        if should_update_password:
            _log_auth_event("password_changed", user=g.user, provider="local")
            flash("Conta atualizada e senha alterada com sucesso!", "success")
        else:
            flash("Conta atualizada com sucesso!", "success")
        return redirect(url_for("main.dashboard"))

    return render_template(
        "auth/change_password.html", hide_govbr_link_fields=is_govbr_linked
    )
