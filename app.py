import os
import secrets
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import Flask, g, redirect, request, session, url_for

from config import build_app_config, _env_flag_is_true
from extensions import csrf, db, limiter, migrate  # noqa: F401 — db re-exported for scripts
from models import User, UserNotification
from routes import inject_current_year, main_bp
from services.govbr_oidc import GovBrOIDCError, is_govbr_oidc_enabled, refresh_access_token
from startup import initialize_database
from time_utils import register_sqlite_adapters

# Re-exportações para compatibilidade com scripts e testes existentes
from startup import ensure_caderno_schema, ensure_project_abep_indicator_column, ensure_task_core_columns, ensure_tutorial_columns  # noqa: F401

TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')


def _extract_origin(url):
    """Extrai o scheme://host[:port] de uma URL; vazio se inválida."""
    if not url:
        return ''
    try:
        parsed = urlparse(url)
    except Exception:
        return ''
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'


def _build_csp_header(nonce, chatbot_origin):
    """CSP restritiva: só executa JS com nonce ou de 'self'; iframes/imgs do chatbot permitidos."""
    frame_extra = f' {chatbot_origin}' if chatbot_origin else ''
    img_extra = f' {chatbot_origin}' if chatbot_origin else ''
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data:{img_extra}; "
        "font-src 'self'; "
        f"frame-src 'self'{frame_extra}; "
        "connect-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'"
    )


# ---------------------------------------------------------------------------
# Request hooks
# ---------------------------------------------------------------------------

def _register_request_hooks(app):
    @app.before_request
    def assign_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.before_request
    def load_logged_in_user():
        session.permanent = True
        user_id = session.get('user_id')
        g.user = None
        if user_id is None:
            return
        g.user = db.session.get(User, user_id)
        if g.user is None:
            session.clear()

    @app.before_request
    def check_govbr_token_expiry():
        if session.get('auth_provider') != 'govbr':
            return
        if not getattr(g, 'user', None):
            return

        access_token_exp = session.get('govbr_access_token_exp')
        if not access_token_exp:
            return

        # Renova com 30s de antecedência para evitar expiração durante a requisição.
        if time.time() < access_token_exp - 30:
            return

        govbr_refresh_token = request.cookies.get('govbr_refresh_token')
        if not govbr_refresh_token:
            session.clear()
            g.user = None
            return redirect(url_for('main.login_page'))

        try:
            new_tokens = refresh_access_token(app.config, refresh_token=govbr_refresh_token)
        except GovBrOIDCError:
            session.clear()
            g.user = None
            return redirect(url_for('main.login_page'))

        expires_in = new_tokens.get('expires_in')
        refresh_expires_in = new_tokens.get('refresh_expires_in')
        if expires_in:
            session['govbr_access_token_exp'] = int(time.time()) + int(expires_in)
        if refresh_expires_in:
            session['govbr_refresh_exp'] = int(time.time()) + int(refresh_expires_in)

        new_refresh_token = new_tokens.get('refresh_token')
        if new_refresh_token:
            g.govbr_new_refresh_token = new_refresh_token
            g.govbr_new_refresh_max_age = int(refresh_expires_in) if refresh_expires_in else None

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        nonce = getattr(g, 'csp_nonce', None)
        if nonce:
            chatbot_origin = _extract_origin(app.config.get('CHATBOT_BASE_URL', ''))
            response.headers['Content-Security-Policy'] = _build_csp_header(nonce, chatbot_origin)
        return response

    @app.after_request
    def apply_govbr_refresh_cookie(response):
        new_refresh_token = getattr(g, 'govbr_new_refresh_token', None)
        if new_refresh_token:
            response.set_cookie(
                'govbr_refresh_token',
                new_refresh_token,
                httponly=True,
                secure=app.config.get('SESSION_COOKIE_SECURE', False),
                samesite='Strict',
                max_age=getattr(g, 'govbr_new_refresh_max_age', None),
            )
        return response


# ---------------------------------------------------------------------------
# Template filters & context processors
# ---------------------------------------------------------------------------

def _register_template_filters(app):
    @app.template_filter('local_time')
    def local_time_filter(dt, fmt='%d/%m %H:%M'):
        """Converte datetime UTC para horário do Brasil e formata."""
        if dt is None:
            return ''
        utc = dt.replace(tzinfo=ZoneInfo('UTC')) if dt.tzinfo is None else dt
        local = utc.astimezone(TIMEZONE_BR)
        return local.strftime(fmt)

    @app.template_filter('local_datetime')
    def local_datetime_filter(dt, fmt='%d/%m/%Y às %H:%M'):
        """Converte datetime UTC para horário do Brasil em formato longo."""
        if dt is None:
            return ''
        utc = dt.replace(tzinfo=ZoneInfo('UTC')) if dt.tzinfo is None else dt
        local = utc.astimezone(TIMEZONE_BR)
        return local.strftime(fmt)


def _register_context_processors(app):
    app.context_processor(inject_current_year)

    @app.context_processor
    def inject_csp_nonce():
        return {'csp_nonce': getattr(g, 'csp_nonce', '')}

    @app.context_processor
    def inject_user_info_to_templates():
        from flask import session as flask_session
        current_user_obj = g.user if hasattr(g, 'user') else None
        is_admin = bool(current_user_obj and current_user_obj.is_admin)
        unread_notifications_count = 0
        if current_user_obj:
            unread_notifications_count = (
                UserNotification.query
                .filter(
                    UserNotification.recipient_user_id == current_user_obj.id,
                    UserNotification.is_read.is_(False),
                )
                .count()
            )
        return {
            'current_user_obj': current_user_obj,
            'is_admin_user': is_admin,
            'unread_notifications_count': unread_notifications_count,
            'govbr_login_enabled': is_govbr_oidc_enabled(app.config),
            'chatbot_enabled': bool(app.config.get('CHATBOT_ENABLED')),
            'chatbot_base_url': str(app.config.get('CHATBOT_BASE_URL', '')).strip().rstrip('/'),
            'tutorial_active': bool(flask_session.get('tutorial_active')),
            'tutorial_section': flask_session.get('tutorial_section', ''),
            # Só consome o flag reset quando o tutorial está ativo; caso contrário
            # o bootstrap do tutorial não roda e o flag seria perdido sem efeito.
            'tutorial_reset': (
                bool(flask_session.pop('tutorial_reset', False))
                if flask_session.get('tutorial_active') else False
            ),
        }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(test_config=None):
    app = Flask(__name__)

    is_debug = app.debug or _env_flag_is_true('FLASK_DEBUG', default='false')
    is_testing = bool(test_config and test_config.get('TESTING'))

    app.config.update(build_app_config(is_testing=is_testing, is_debug=is_debug))

    if test_config:
        app.config.update(test_config)

    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        from config import _resolve_database_uri
        app.config['SQLALCHEMY_DATABASE_URI'] = _resolve_database_uri()

    if str(app.config.get('SQLALCHEMY_DATABASE_URI', '')).startswith('sqlite:'):
        register_sqlite_adapters()

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(main_bp)
    _register_request_hooks(app)
    _register_template_filters(app)
    _register_context_processors(app)

    if not app.config.get('SKIP_STARTUP_DB_INIT'):
        with app.app_context():
            try:
                startup_summary = initialize_database()
                if startup_summary['column_added']:
                    print('Coluna project.abep_indicator criada com sucesso.')
                print(f"Catalogo de objetivos sincronizado: {startup_summary['sync_summary']}")
                tutorial_cols = ensure_tutorial_columns()
                if tutorial_cols:
                    print(f"Colunas de tutorial criadas: {tutorial_cols}")
            except Exception as exc:
                print(f'Erro durante a inicialização/verificação do banco de dados em app.py: {exc}')

    return app


app = create_app()


if __name__ == '__main__':
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
        host='0.0.0.0',
        port=5002,
    )
