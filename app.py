from urllib.parse import quote_plus
from dotenv import load_dotenv
from flask import Flask, session, g
from flask_migrate import Migrate
import os
from zoneinfo import ZoneInfo
from sqlalchemy import inspect, text

# Import db e User de models.py para inicialização
from models import db, User # User é crucial aqui
from objective_catalog import sync_goal_catalog_to_db
# Importar o Blueprint das rotas e a função context_processor de routes.py
from routes import main_bp, inject_current_year

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', '***REMOVED***')

# Ordem de prioridade para configuração de banco:
# 1) DATABASE_URL explícita
# 2) MySQL via DB_USER/DB_PASSWORD/DB_NAME
# 3) SQLite local (padrão para desenvolvimento)
database_url = os.getenv('DATABASE_URL')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_name = os.getenv('DB_NAME')

if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
elif db_user and db_password and db_name:
    password = quote_plus(db_password)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{db_user}:{password}@localhost/{db_name}"
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'projetosrj.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Desativa o rastreamento de modificações

db.init_app(app)

migrate = Migrate(app, db) # Mantenha para futuras migrações de outras tabelas

app.register_blueprint(main_bp)
app.context_processor(inject_current_year) # Para o ano atual no rodapé


# Hook para carregar o usuário logado antes de cada request
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    g.user = None
    if user_id is not None:
        g.user = User.query.get(user_id)
        if g.user is None: # Usuário na sessão não existe mais no DB
            session.clear()


# Fuso horário do Brasil (Rio de Janeiro) para exibição de datas
TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')

@app.template_filter('local_time')
def local_time_filter(dt, fmt='%d/%m %H:%M'):
    """Converte datetime UTC (naive) para horário do Brasil e formata."""
    if dt is None:
        return ''
    if dt.tzinfo is None:
        utc = dt.replace(tzinfo=ZoneInfo('UTC'))
    else:
        utc = dt
    local = utc.astimezone(TIMEZONE_BR)
    return local.strftime(fmt)

@app.template_filter('local_datetime')
def local_datetime_filter(dt, fmt='%d/%m/%Y às %H:%M'):
    """Converte datetime UTC para Brasil, formato longo."""
    if dt is None:
        return ''
    if dt.tzinfo is None:
        utc = dt.replace(tzinfo=ZoneInfo('UTC'))
    else:
        utc = dt
    local = utc.astimezone(TIMEZONE_BR)
    return local.strftime(fmt)


# Processador de contexto para injetar informações do usuário nos templates
@app.context_processor
def inject_user_info_to_templates():
    current_user_obj = g.user if hasattr(g, 'user') else None
    is_admin = False
    if current_user_obj:
        is_admin = current_user_obj.is_admin
    return dict(
        current_user_obj=current_user_obj,
        is_admin_user=is_admin
    )


def ensure_project_abep_indicator_column():
    """
    Garante a coluna project.abep_indicator em bancos ja existentes.
    """
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


with app.app_context():
    try:
        # create_all e idempotente: cria apenas tabelas faltantes.
        db.create_all()
        column_added = ensure_project_abep_indicator_column()
        if column_added:
            print("Coluna project.abep_indicator criada com sucesso.")
        sync_summary = sync_goal_catalog_to_db(commit=True)
        print(f"Catalogo de objetivos sincronizado: {sync_summary}")
    except Exception as e:
        print(f"Erro durante a inicialização/verificação do banco de dados em app.py: {str(e)}")

if __name__ == '__main__':
    # Roda a aplicação na porta 5001
    app.run(debug=True,host='0.0.0.0', port=5002)
