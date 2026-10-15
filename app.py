import os
import secrets
import time
from typing import TypedDict
from urllib.parse import urlparse

from flask import (
    Flask,
    Response,
    current_app,
    flash,
    g,
    redirect,
    request,
    session,
    url_for,
)

from sqlalchemy.engine import make_url

from config import build_app_config, _env_flag_is_true, _env_int
from extensions import (
    csrf,
    db,
    limiter,
    migrate,
)  # noqa: F401 — db re-exported for scripts
from models import User, UserNotification
from routes import inject_current_year, main_bp
from services.govbr_oidc import is_govbr_oidc_enabled
from services.integrations_status import log_integration_statuses
from startup import verify_schema_version
from time_utils import register_sqlite_adapters


def _extract_origin(url):
    """Extrai o scheme://host[:port] de uma URL; vazio se inválida."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _build_csp_header(nonce, chatbot_origin):
    """CSP restritiva: só executa JS com nonce ou de 'self'; iframes/imgs do chatbot permitidos."""
    frame_extra = f" {chatbot_origin}" if chatbot_origin else ""
    img_extra = f" {chatbot_origin}" if chatbot_origin else ""
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


def _sessao_expirou_teto_absoluto() -> bool:
    """Teto absoluto de login: o refresh deslizante do cookie não o estende.

    Sessão sem ``login_at`` (criada antes deste deploy) conta como expirada —
    força um único re-login após o deploy.
    """
    teto_segundos = current_app.permanent_session_lifetime.total_seconds()
    return time.time() - session.get("login_at", 0) > teto_segundos


def _resposta_sessao_expirada() -> Response | tuple[Response, int]:
    """401 JSON p/ API (evita loop de 302 na SPA); redirect p/ login no resto."""
    from routes.api import fail, wants_json

    e_api = request.path.startswith("/api/") or wants_json()
    # Só GET vira next: reenviar o usuário a uma URL de POST daria 405 após o login.
    proximo = request.url if request.method == "GET" else None
    session.clear()
    g.user = None
    if e_api:
        return fail("Sessão expirada.", status=401, code="unauthenticated")
    flash("Sessão expirada. Faça login novamente.", "warning")
    return redirect(url_for("main.login_page", next=proximo))


def _register_request_hooks(app):
    @app.before_request
    def assign_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.before_request
    def load_logged_in_user():
        session.permanent = True
        user_id = session.get("user_id")
        g.user = None
        if user_id is None:
            return
        if _sessao_expirou_teto_absoluto():
            return _resposta_sessao_expirada()
        g.user = db.session.get(User, user_id)
        if g.user is None:
            session.clear()
            return
        # Soft-delete C4: usuário removido não usa o app, mesmo que autentique.
        # Invalida a sessão atual e bloqueia re-login (local/gov.br) no próximo
        # request — o histórico permanece atribuído a ele, mas o acesso some.
        if g.user.deleted_at is not None:
            session.clear()
            g.user = None

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        nonce = getattr(g, "csp_nonce", None)
        if nonce:
            chatbot_origin = _extract_origin(app.config.get("CHATBOT_BASE_URL", ""))
            response.headers["Content-Security-Policy"] = _build_csp_header(
                nonce, chatbot_origin
            )
        return response


def _register_context_processors(app):
    app.context_processor(inject_current_year)

    @app.context_processor
    def inject_csp_nonce():
        return {"csp_nonce": getattr(g, "csp_nonce", "")}

    @app.context_processor
    def inject_user_info_to_templates():
        from flask import session as flask_session

        current_user_obj = g.user if hasattr(g, "user") else None
        is_admin = bool(current_user_obj and current_user_obj.is_admin)
        unread_notifications_count = 0
        if current_user_obj:
            unread_notifications_count = UserNotification.query.filter(
                UserNotification.recipient_user_id == current_user_obj.id,
                UserNotification.is_read.is_(False),
            ).count()
        return {
            "current_user_obj": current_user_obj,
            "is_admin_user": is_admin,
            "unread_notifications_count": unread_notifications_count,
            "govbr_login_enabled": is_govbr_oidc_enabled(app.config),
            "chatbot_enabled": bool(app.config.get("CHATBOT_ENABLED")),
            "chatbot_base_url": str(app.config.get("CHATBOT_BASE_URL", ""))
            .strip()
            .rstrip("/"),
        }


_FLASK_DB_SUBCOMMANDS = frozenset(
    {
        "upgrade",
        "downgrade",
        "stamp",
        "current",
        "check",
        "heads",
        "history",
        "migrate",
        "revision",
        "merge",
        "show",
        "branches",
        "edit",
        "init",
    }
)


def _is_flask_db_cli() -> bool:
    """`flask db upgrade` importa o app: verificar schema aqui criaria impasse
    (impossível migrar um banco que impede o boot). Detecta por `db <sub>` no
    argv para cobrir também `python -m flask ...` e flags extras."""
    import sys

    argv = sys.argv
    if "db" not in argv:
        return False
    db_index = argv.index("db")
    subcommand = argv[db_index + 1] if len(argv) > db_index + 1 else ""
    return subcommand in _FLASK_DB_SUBCOMMANDS


def _verify_schema_on_boot(app: Flask) -> None:
    """Boot só VERIFICA o schema (Sprint 5.3); migrar é passo de deploy."""
    if _is_flask_db_cli():
        return
    with app.app_context():
        revision = verify_schema_version()
        if revision:
            app.logger.info("Schema verificado: alembic_version=%s", revision)


def _apply_proxy_fix(app: Flask) -> None:
    """Atrás de proxy o scheme/Host reais só chegam via X-Forwarded-*; sem isto
    url_for(_external=True) e o redirect_uri derivado usam o host interno.
    Só confiar nos headers onde o proxy os REESCREVE (daí o default OFF)."""
    if not app.config.get("PROXYFIX_ENABLED"):
        return

    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=int(app.config.get("PROXYFIX_X_FOR", 1)),
        x_proto=int(app.config.get("PROXYFIX_X_PROTO", 1)),
        x_host=int(app.config.get("PROXYFIX_X_HOST", 1)),
        x_port=int(app.config.get("PROXYFIX_X_PORT", 0)),
        x_prefix=int(app.config.get("PROXYFIX_X_PREFIX", 0)),
    )


def ensure_sqlite_dir(database_uri: str) -> None:
    """Cria a pasta do arquivo SQLite (ex.: ``instance/``), que não vem no clone.

    Sem ela o primeiro ``flask db upgrade`` falha com "unable to open database
    file", sem dizer qual pasta falta. MySQL e SQLite em memória: no-op.
    Ex.: ``ensure_sqlite_dir("sqlite:////tmp/x/app.db")`` cria ``/tmp/x``.
    """
    if not database_uri.startswith("sqlite"):
        return
    caminho = make_url(database_uri).database
    if not caminho or caminho == ":memory:" or caminho.startswith("file:"):
        return
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)


def create_app(test_config=None):
    app = Flask(__name__)

    is_debug = app.debug or _env_flag_is_true("FLASK_DEBUG", default="false")
    is_testing = bool(test_config and test_config.get("TESTING"))

    app.config.update(build_app_config(is_testing=is_testing, is_debug=is_debug))

    if test_config:
        app.config.update(test_config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        from config import _resolve_database_uri

        app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()

    if str(app.config.get("SQLALCHEMY_DATABASE_URI", "")).startswith("sqlite:"):
        register_sqlite_adapters()
        ensure_sqlite_dir(str(app.config["SQLALCHEMY_DATABASE_URI"]))

    _apply_proxy_fix(app)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(main_bp)
    _register_request_hooks(app)
    _register_context_processors(app)

    # TESTING usa create_all sem alembic_version; SKIP_STARTUP_DB_INIT cobre
    # scripts de backfill que rodam contra banco em migração.
    if not app.config.get("TESTING") and not app.config.get("SKIP_STARTUP_DB_INIT"):
        _verify_schema_on_boot(app)
        log_integration_statuses(app)

    return app


class DevServerOptions(TypedDict):
    host: str
    port: int
    debug: bool


def dev_server_options() -> DevServerOptions:
    """Opções do ``python app.py`` (só dev; produção sobe por gunicorn).

    Default 127.0.0.1: com FLASK_DEBUG ligado o debugger do Werkzeug executa
    código — em 0.0.0.0 qualquer máquina da rede chegaria nele.
    Ex.: ``APP_HOST=0.0.0.0 APP_PORT=8000 python app.py``.
    """
    return DevServerOptions(
        host=os.getenv("APP_HOST", "").strip() or "127.0.0.1",
        port=_env_int("APP_PORT", default=5002),
        debug=_env_flag_is_true("FLASK_DEBUG", default="false"),
    )


app = create_app()


if __name__ == "__main__":
    app.run(**dev_server_options())
