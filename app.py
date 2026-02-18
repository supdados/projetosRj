import os
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, g, session
from flask_migrate import Migrate
from sqlalchemy import inspect, text

from models import User, db
from objective_catalog import sync_goal_catalog_to_db
from routes import inject_current_year, main_bp

load_dotenv()

TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')
migrate = Migrate()


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


def _env_flag_is_true(name, default='false'):
    raw = os.getenv(name, default)
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def ensure_project_abep_indicator_column():
    """Garante a coluna project.abep_indicator em bancos existentes."""
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if 'project' not in table_names:
        return False

    column_names = {column["name"] for column in inspector.get_columns('project')}
    if 'abep_indicator' in column_names:
        return False

    db.session.execute(text("ALTER TABLE project ADD COLUMN abep_indicator VARCHAR(255)"))
    db.session.commit()
    return True


def initialize_database():
    """
    Inicializa estrutura mínima do banco:
    - cria tabelas faltantes;
    - garante coluna ABEP em bancos legados;
    - sincroniza catálogo de objetivo/resultado/indicador.
    """
    db.create_all()
    column_added = ensure_project_abep_indicator_column()
    sync_summary = sync_goal_catalog_to_db(commit=True)
    return {
        'column_added': column_added,
        'sync_summary': sync_summary,
    }


def _register_request_hooks(app):
    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        g.user = None
        if user_id is None:
            return
        g.user = db.session.get(User, user_id)
        if g.user is None:
            session.clear()


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
    def inject_user_info_to_templates():
        current_user_obj = g.user if hasattr(g, 'user') else None
        is_admin = bool(current_user_obj and current_user_obj.is_admin)
        return {
            'current_user_obj': current_user_obj,
            'is_admin_user': is_admin,
        }


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY', '***REMOVED***'),
        SQLALCHEMY_DATABASE_URI=_resolve_database_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SKIP_STARTUP_DB_INIT=_env_flag_is_true('SKIP_STARTUP_DB_INIT', default='false'),
    )

    if test_config:
        app.config.update(test_config)

    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        app.config['SQLALCHEMY_DATABASE_URI'] = _resolve_database_uri()

    db.init_app(app)
    migrate.init_app(app, db)

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
            except Exception as exc:
                print(f'Erro durante a inicialização/verificação do banco de dados em app.py: {exc}')

    return app


app = create_app()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
