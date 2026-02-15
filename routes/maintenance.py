import os

from flask import current_app, jsonify, request, send_from_directory, url_for
from sqlalchemy import inspect, text

from models import db
from objective_catalog import sync_goal_catalog_to_db

from .blueprint import main_bp
# Rota específica para servir o favicon
@main_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(main_bp.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')
@main_bp.route('/setup_db')
# @login_required # Opcional: proteger esta rota
# @admin_required # Opcional: proteger esta rota
def setup_db():
    # Lembre-se que a tabela 'user' foi criada manualmente.
    # db.create_all() aqui NÃO vai recriar 'user' se ela já existir.
    # Só criaria outras tabelas dos modelos que ainda não existem.
    from flask import current_app # Importar aqui para evitar import circular no topo se routes for grande
    try:
        from sqlalchemy import inspect # Importar aqui
        inspector = inspect(db.engine)
        
        tabelas_existentes = inspector.get_table_names()
        tabela_project_existe = 'project' in tabelas_existentes
        tabela_user_existe = 'user' in tabelas_existentes
        force_creation = request.args.get('force', 'false').lower() == 'true'
        
        resultado = {
            "status": "success", "mensagem": "",
            "detalhes": {
                "tabelas_existentes": tabelas_existentes,
                "tabela_project_existe": tabela_project_existe,
                "tabela_user_existe": tabela_user_existe,
                "banco_de_dados": current_app.config['SQLALCHEMY_DATABASE_URI'],
                "ambiente": "Google App Engine" if os.getenv('GAE_ENV', '').startswith('standard') else "Desenvolvimento Local"
            }
        }
        
        # Se forçar ou se alguma das tabelas principais (project, user) não existir
        if force_creation or not tabela_project_existe or not tabela_user_existe:
            # CUIDADO: db.drop_all() APAGA TODOS OS DADOS. NÃO use em produção sem backup.
            # if force_creation:
            #     # db.drop_all() # Comentado por segurança
            #     resultado["mensagem"] += " (DROP ALL FOI COMENTADO POR SEGURANÇA) "
            
            db.create_all() # Cria tabelas FALTANTES. Não recria as existentes.
            resultado["mensagem"] += "Banco de dados configurado. Tabelas faltantes (re)criadas."
            resultado["detalhes"]["tabelas_criadas"] = True
        else:
            resultado["mensagem"] = "As tabelas principais já existem. Use ?force=true para tentar recriar tabelas faltantes (sem apagar dados existentes)."
            resultado["detalhes"]["tabelas_criadas"] = False

        sync_summary = sync_goal_catalog_to_db(commit=True)
        resultado["detalhes"]["catalogo_objetivos_sync"] = sync_summary

        # Garantir coluna de Indicador ABEP em bancos existentes
        inspector = inspect(db.engine)  # Recria para evitar cache de metadata antiga
        table_names_after = inspector.get_table_names()
        project_columns = {col["name"] for col in inspector.get_columns('project')} if 'project' in table_names_after else set()
        if 'project' in table_names_after and 'abep_indicator' not in project_columns:
            db.session.execute(text("ALTER TABLE project ADD COLUMN abep_indicator VARCHAR(255)"))
            db.session.commit()
            resultado["detalhes"]["abep_indicator_column"] = "created"
        else:
            resultado["detalhes"]["abep_indicator_column"] = "exists"
        
        accept_header = request.headers.get('Accept', '')
        if 'application/json' in accept_header:
            return jsonify(resultado)
        
        html_response = f"""
        <h1>Status do Banco de Dados</h1>
        <p><strong>Status:</strong> {resultado['status']}</p>
        <p><strong>Mensagem:</strong> {resultado['mensagem']}</p>
        <h2>Detalhes</h2><ul>
            <li><strong>Ambiente:</strong> {resultado['detalhes']['ambiente']}</li>
            <li><strong>Banco de Dados:</strong> {resultado['detalhes']['banco_de_dados']}</li>
            <li><strong>Tabela 'project' Existe:</strong> {resultado['detalhes']['tabela_project_existe']}</li>
            <li><strong>Tabela 'user' Existe:</strong> {resultado['detalhes']['tabela_user_existe']}</li>
            <li><strong>Tabelas Existentes:</strong> {', '.join(resultado['detalhes']['tabelas_existentes'])}</li>
            <li><strong>Sync Catálogo Objetivos:</strong> {resultado['detalhes'].get('catalogo_objetivos_sync', {})}</li>
        </ul>
        <p><a href="{url_for('main.home')}">Voltar</a> | <a href="{url_for('main.setup_db', force='true')}">Forçar criação de tabelas faltantes</a></p>
        """
        return html_response
            
    except Exception as e:
        error_msg = f"Erro ao configurar banco de dados: {str(e)}"
        current_app.logger.error(f"Erro em /setup_db: {error_msg}", exc_info=True)
        return jsonify({"status": "error", "mensagem": error_msg}) if 'application/json' in request.headers.get('Accept', '') else error_msg
