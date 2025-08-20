from dotenv import load_dotenv
from flask import Flask, session, g
from flask_migrate import Migrate
import os
import pymysql

# Import db e User de models.py para inicialização
from models import db, User # User é crucial aqui
# Importar o Blueprint das rotas e a função context_processor de routes.py
from routes import main_bp, inject_current_year

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', '***REMOVED***')

app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://"+os.getenv('DB_USER')+":"+os.getenv('DB_PASSWORD')+'@localhost/'+os.getenv('DB_NAME')
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


# Bloco de db.create_all() - Opcional se todas as tabelas já existem
# Como você já tem 'user' e 'project', etc., este bloco provavelmente não fará nada
# a menos que você adicione NOVOS modelos no futuro.
with app.app_context():
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.get_table_names(): # Só executa se NENHUMA tabela existir
            print("Banco de dados parece estar vazio. Criando todas as tabelas definidas nos modelos...")
            db.create_all() # Não recriará tabelas existentes como 'user' ou 'project'
            print("Tabelas criadas com sucesso!")
    except Exception as e:
        print(f"Erro durante a inicialização/verificação do banco de dados em app.py: {str(e)}")

if __name__ == '__main__':
    # Roda a aplicação na porta 5001
    app.run(debug=True,host='0.0.0.0', port=5002)
