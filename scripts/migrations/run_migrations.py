#!/usr/bin/env python3
"""
Script Unificado de Migração de Banco de Dados

Este script executa as seguintes migrações em sequência:
1. Migra os dados do campo 'area_responsavel' (tabela User) para a nova tabela 'user_areas'.
2. Cria a tabela 'project_history' para o rastreamento de ações em projetos.
3. Sincroniza o catalogo canonico de objetivo/resultado/indicador.
4. Garante a coluna 'abep_indicator' na tabela 'project'.

Uso:
    python3 scripts/migrations/run_migrations.py
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text
from app import app, db
# Importe todos os modelos necessários de uma vez
from models import User, UserArea, ProjectHistory, Project
from objective_catalog import sync_goal_catalog_to_db
from time_utils import utc_now

def migrate_user_areas():
    """
    Migra dados de User.area_responsavel para a tabela UserArea.
    Retorna True em caso de sucesso, False em caso de erro.
    """
    print("\n-- [1/4] Iniciando migração de áreas de usuários...")
    try:
        # Garante que a tabela user_areas exista
        db.create_all()

        users = User.query.all()
        migrated_count = 0
        
        for user in users:
            # Pula se o usuário já tiver áreas na nova tabela para evitar duplicatas
            if UserArea.query.filter_by(user_id=user.id).first():
                continue
            
            # Se o campo antigo tiver valor, cria a nova entrada
            if user.area_responsavel:
                new_user_area = UserArea(user_id=user.id, area=user.area_responsavel)
                db.session.add(new_user_area)
                migrated_count += 1
        
        db.session.commit()
        print(f"   ✓ Sucesso: {migrated_count} novas áreas foram migradas.")
        return True

    except Exception as e:
        db.session.rollback()
        print(f"   ✗ ERRO na migração de áreas: {e}")
        return False

def create_history_table():
    """
    Cria e verifica a tabela project_history.
    Retorna True em caso de sucesso, False em caso de erro.
    """
    print("\n-- [2/4] Iniciando criação da tabela de histórico de projetos...")
    try:
        # Garante que a tabela project_history exista
        db.create_all()

        # Testa a inserção para garantir que a tabela está funcional
        project = Project.query.first()
        user = User.query.first()
        
        # Só realiza o teste se houver dados para usar
        if project and user:
            test_entry = ProjectHistory(
                project_id=project.id,
                user_id=user.id,
                action_type='migration',
                action_description='Sistema de histórico instalado com sucesso!',
                timestamp=utc_now()
            )
            db.session.add(test_entry)
        
        db.session.commit()
        print("   ✓ Sucesso: Tabela 'project_history' criada e verificada.")
        return True

    except Exception as e:
        db.session.rollback()
        print(f"   ✗ ERRO na criação da tabela de histórico: {e}")
        return False


def sync_goal_catalog():
    """
    Sincroniza o catalogo fixo de objetivo/resultado/indicador no banco.
    """
    print("\n-- [3/4] Sincronizando catalogo de objetivos/resultados/indicadores...")
    try:
        db.create_all()
        summary = sync_goal_catalog_to_db(commit=True)
        print(f"   ✓ Sucesso: {summary}")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"   ✗ ERRO na sincronizacao do catalogo: {e}")
        return False


def ensure_abep_indicator_column():
    """
    Garante a coluna project.abep_indicator em bancos existentes.
    """
    print("\n-- [4/4] Verificando coluna project.abep_indicator...")
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        if 'project' not in tables:
            print("   ✓ Tabela 'project' ainda nao existe (sera criada pelo create_all quando necessario).")
            return True

        columns = {col["name"] for col in inspector.get_columns('project')}
        if 'abep_indicator' in columns:
            print("   ✓ Coluna 'abep_indicator' ja existe.")
            return True

        db.session.execute(text("ALTER TABLE project ADD COLUMN abep_indicator VARCHAR(255)"))
        db.session.commit()
        print("   ✓ Coluna 'abep_indicator' criada com sucesso.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"   ✗ ERRO ao criar coluna abep_indicator: {e}")
        return False

if __name__ == '__main__':
    # Executa tudo dentro do contexto da aplicação Flask
    with app.app_context():
        print("=" * 60)
        print("INICIANDO SCRIPT DE MIGRAÇÃO DE BANCO DE DADOS")
        print("=" * 60)

        # Etapa 1: Migrar áreas de usuários
        if not migrate_user_areas():
            print("\n!! Migração interrompida devido a um erro.")
            exit(1) # Sai com código de erro

        # Etapa 2: Criar tabela de histórico
        if not create_history_table():
            print("\n!! Migração interrompida devido a um erro.")
            exit(1) # Sai com código de erro

        # Etapa 3: Sincronizar catalogo fixo
        if not sync_goal_catalog():
            print("\n!! Migração interrompida devido a um erro.")
            exit(1) # Sai com código de erro

        # Etapa 4: Garantir coluna Indicador ABEP
        if not ensure_abep_indicator_column():
            print("\n!! Migração interrompida devido a um erro.")
            exit(1) # Sai com código de erro

        print("\n" + "=" * 60)
        print("🎉 TODAS AS MIGRAÇÕES FORAM CONCLUÍDAS COM SUCESSO! 🎉")
        print("=" * 60)
        exit(0) # Sai com código de sucesso
