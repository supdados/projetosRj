import os
from datetime import timedelta
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _env_flag_is_true(name, default='false'):
    raw = os.getenv(name, default)
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_int(name, default=10):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _default_sqlite_uri():
    basedir = os.path.abspath(os.path.dirname(__file__))
    return 'sqlite:///' + os.path.join(basedir, 'instance', 'projetosrj.db')


def _resolve_database_uri(explicit_uri=None):
    if explicit_uri:
        return explicit_uri

    database_url = os.getenv('DATABASE_URL')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    if database_url:
        return database_url
    if db_user and db_password and db_name:
        password = quote_plus(db_password)
        return f"mysql+pymysql://{db_user}:{password}@localhost/{db_name}"
    return _default_sqlite_uri()


def _resolve_secret_key(*, is_testing=False, is_debug=False):
    secret = os.getenv('SECRET_KEY', '').strip()
    if secret:
        return secret
    if is_testing or is_debug:
        return 'dev-only-insecure-key'
    raise RuntimeError(
        'SECRET_KEY não definida. Configure via variável de ambiente antes de rodar em produção.'
    )


def build_app_config(*, is_testing=False, is_debug=False):
    """Retorna o dicionário completo de configuração do Flask."""
    return dict(
        SECRET_KEY=_resolve_secret_key(is_testing=is_testing, is_debug=is_debug),
        SQLALCHEMY_DATABASE_URI=_resolve_database_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB
        WTF_CSRF_ENABLED=_env_flag_is_true('WTF_CSRF_ENABLED', default='true'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=_env_flag_is_true('SESSION_COOKIE_SECURE', default='false'),
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SKIP_STARTUP_DB_INIT=_env_flag_is_true('SKIP_STARTUP_DB_INIT', default='false'),
        GOVBR_OIDC_ENABLED=_env_flag_is_true('GOVBR_OIDC_ENABLED', default='false'),
        GOVBR_OIDC_BASE_URL=os.getenv('GOVBR_OIDC_BASE_URL', ''),
        GOVBR_OIDC_REALM=os.getenv('GOVBR_OIDC_REALM', ''),
        GOVBR_OIDC_CLIENT_ID=os.getenv('GOVBR_OIDC_CLIENT_ID', ''),
        GOVBR_OIDC_CLIENT_SECRET=os.getenv('GOVBR_OIDC_CLIENT_SECRET', ''),
        GOVBR_OIDC_REDIRECT_URI=os.getenv('GOVBR_OIDC_REDIRECT_URI', 'http://localhost:5002/auth/govbr/callback'),
        GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI=os.getenv('GOVBR_OIDC_POST_LOGOUT_REDIRECT_URI', 'http://localhost:5002/login'),
        GOVBR_OIDC_FEDERATED_LOGOUT_ENABLED=_env_flag_is_true('GOVBR_OIDC_FEDERATED_LOGOUT_ENABLED', default='true'),
        GOVBR_OIDC_SCOPE=os.getenv('GOVBR_OIDC_SCOPE', 'openid profile email'),
        GOVBR_OIDC_TIMEOUT_SECONDS=_env_int('GOVBR_OIDC_TIMEOUT_SECONDS', default=10),
        GOOGLE_CALENDAR_ENABLED=_env_flag_is_true('GOOGLE_CALENDAR_ENABLED', default='true'),
        GOOGLE_CALENDAR_CLIENT_SECRET_FILE=os.getenv('GOOGLE_CALENDAR_CLIENT_SECRET_FILE', 'config/client_secret.json'),
        GOOGLE_CALENDAR_PUBLIC_BASE_URL=os.getenv('GOOGLE_CALENDAR_PUBLIC_BASE_URL', ''),
        GOOGLE_CALENDAR_REDIRECT_URI=os.getenv('GOOGLE_CALENDAR_REDIRECT_URI', ''),
        GOOGLE_CALENDAR_WEBHOOK_URL=os.getenv('GOOGLE_CALENDAR_WEBHOOK_URL', ''),
        GOOGLE_CALENDAR_SCOPE=os.getenv(
            'GOOGLE_CALENDAR_SCOPE',
            'openid email https://www.googleapis.com/auth/calendar.events',
        ),
        GOOGLE_CALENDAR_TIMEOUT_SECONDS=_env_int('GOOGLE_CALENDAR_TIMEOUT_SECONDS', default=10),
        GOOGLE_CALENDAR_DEFAULT_ID=os.getenv('GOOGLE_CALENDAR_DEFAULT_ID', 'primary'),
        GOOGLE_CALENDAR_WATCH_TTL_SECONDS=_env_int('GOOGLE_CALENDAR_WATCH_TTL_SECONDS', default=604800),
        CHATBOT_ENABLED=_env_flag_is_true('CHATBOT_ENABLED', default='false'),
        CHATBOT_BASE_URL=os.getenv('CHATBOT_BASE_URL', '').strip().rstrip('/'),
        CHATBOT_PORTAL_API_KEY=os.getenv('CHATBOT_PORTAL_API_KEY', '').strip(),
        CHATBOT_TIMEOUT_SECONDS=_env_int('CHATBOT_TIMEOUT_SECONDS', default=10),
    )
