#!/usr/bin/env python3
"""
Script de Migração - Adicionar campo duration_days no MySQL
Para uso em ambiente Linux/Produção

Execute com: python migrate_mysql_duration_days.py
"""

import pymysql
import sys
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env
load_dotenv()

# Configurações do banco MySQL (do .env ou padrão)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'project_management')

def print_header(message):
    """Imprime cabeçalho formatado"""
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70)

def print_success(message):
    """Imprime mensagem de sucesso"""
    print(f"✓ {message}")

def print_error(message):
    """Imprime mensagem de erro"""
    print(f"✗ {message}")

def print_info(message):
    """Imprime mensagem informativa"""
    print(f"ℹ {message}")

def check_column_exists(cursor, table_name, column_name):
    """Verifica se uma coluna existe na tabela"""
    cursor.execute(f"""
        SELECT COUNT(*) 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = '{DB_NAME}' 
        AND TABLE_NAME = '{table_name}' 
        AND COLUMN_NAME = '{column_name}'
    """)
    result = cursor.fetchone()
    return result[0] > 0

def migrate():
    """Função principal de migração"""
    connection = None
    
    try:
        print_header("MIGRAÇÃO MYSQL - Adicionar campo duration_days")
        
        # Conectar ao MySQL
        print_info(f"Conectando ao MySQL: {DB_USER}@{DB_HOST}/{DB_NAME}...")
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        print_success("Conectado ao MySQL com sucesso!")
        
        cursor = connection.cursor()
        
        # Verificar se a tabela StageTemplateItem existe
        print_info("Verificando se a tabela StageTemplateItem existe...")
        cursor.execute(f"""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = '{DB_NAME}' 
            AND TABLE_NAME = 'StageTemplateItem'
        """)
        result = cursor.fetchone()
        
        if result['count'] == 0:
            print_error("Tabela StageTemplateItem não encontrada!")
            print_info("A tabela será criada automaticamente pelo Flask/SQLAlchemy")
            print_info("Execute o aplicativo Flask primeiro para criar as tabelas")
            return False
        
        print_success("Tabela StageTemplateItem encontrada!")
        
        # Verificar se a coluna já existe
        print_info("Verificando se a coluna 'duration_days' já existe...")
        if check_column_exists(cursor, 'StageTemplateItem', 'duration_days'):
            print_success("Coluna 'duration_days' já existe! Nada a fazer.")
            
            # Mostrar estatísticas
            cursor.execute("SELECT COUNT(*) as count FROM StageTemplateItem")
            result = cursor.fetchone()
            print_info(f"Total de itens de template: {result['count']}")
            
            return True
        
        print_info("Coluna 'duration_days' não existe. Iniciando migração...")
        
        # Adicionar a coluna
        print_info("Adicionando coluna 'duration_days' à tabela StageTemplateItem...")
        cursor.execute("""
            ALTER TABLE StageTemplateItem 
            ADD COLUMN duration_days INT NOT NULL DEFAULT 1
            COMMENT 'Duração da etapa em dias úteis'
        """)
        print_success("Coluna 'duration_days' adicionada com sucesso!")
        
        # Verificar registros existentes
        cursor.execute("SELECT COUNT(*) as count FROM StageTemplateItem")
        result = cursor.fetchone()
        total_items = result['count']
        
        if total_items > 0:
            print_info(f"Atualizando {total_items} item(ns) existente(s) com valor padrão...")
            # Não precisa fazer UPDATE porque já definimos DEFAULT 1
            print_success(f"Todos os {total_items} itens configurados com duração padrão de 1 dia")
        else:
            print_info("Nenhum item de template existente")
        
        # Commit das mudanças
        connection.commit()
        print_success("Migração concluída e commitada!")
        
        # Mostrar estrutura da tabela
        print_info("\nEstrutura atualizada da tabela StageTemplateItem:")
        cursor.execute("DESCRIBE StageTemplateItem")
        columns = cursor.fetchall()
        
        print("\n" + "-" * 70)
        print(f"{'Campo':<20} {'Tipo':<20} {'Null':<10} {'Default':<10}")
        print("-" * 70)
        for col in columns:
            field = col['Field']
            col_type = col['Type']
            null = col['Null']
            default = col['Default'] if col['Default'] is not None else 'NULL'
            print(f"{field:<20} {col_type:<20} {null:<10} {default:<10}")
        print("-" * 70)
        
        return True
        
    except pymysql.Error as e:
        print_error(f"Erro MySQL: {e}")
        if connection:
            connection.rollback()
        return False
        
    except Exception as e:
        print_error(f"Erro inesperado: {e}")
        if connection:
            connection.rollback()
        return False
        
    finally:
        if connection:
            connection.close()
            print_info("Conexão MySQL fechada")

def verify_env_variables():
    """Verifica se as variáveis de ambiente estão configuradas"""
    print_header("VERIFICAÇÃO DE CONFIGURAÇÃO")
    
    missing_vars = []
    
    if not os.getenv('DB_USER'):
        print_error("DB_USER não configurado no .env")
        missing_vars.append('DB_USER')
    else:
        print_success(f"DB_USER: {os.getenv('DB_USER')}")
    
    if not os.getenv('DB_PASSWORD'):
        print_error("DB_PASSWORD não configurado no .env")
        missing_vars.append('DB_PASSWORD')
    else:
        print_success("DB_PASSWORD: [CONFIGURADO]")
    
    if not os.getenv('DB_NAME'):
        print_error("DB_NAME não configurado no .env")
        missing_vars.append('DB_NAME')
    else:
        print_success(f"DB_NAME: {os.getenv('DB_NAME')}")
    
    if os.getenv('DB_HOST'):
        print_success(f"DB_HOST: {os.getenv('DB_HOST')}")
    else:
        print_info(f"DB_HOST: localhost (padrão)")
    
    if missing_vars:
        print_error("\nVariáveis faltando no arquivo .env:")
        for var in missing_vars:
            print(f"  - {var}")
        print_info("\nCrie ou edite o arquivo .env com as credenciais do MySQL")
        return False
    
    return True

if __name__ == '__main__':
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║         MIGRAÇÃO MYSQL - Campo duration_days                     ║")
    print("║         Ambiente: Linux/Produção                                 ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    
    # Verificar variáveis de ambiente
    if not verify_env_variables():
        print_error("\nMigração abortada: configuração incompleta")
        sys.exit(1)
    
    # Confirmar execução
    print_header("CONFIRMAÇÃO")
    print_info(f"Banco de dados: {DB_NAME}")
    print_info(f"Host: {DB_HOST}")
    print_info(f"Usuário: {DB_USER}")
    print("\nEsta operação irá:")
    print("  1. Adicionar a coluna 'duration_days' na tabela StageTemplateItem")
    print("  2. Definir valor padrão 1 (um dia) para todos os registros")
    print("  3. Fazer commit das alterações no banco de dados")
    
    resposta = input("\nDeseja continuar? (s/N): ").strip().lower()
    
    if resposta not in ['s', 'sim', 'y', 'yes']:
        print_info("Migração cancelada pelo usuário")
        sys.exit(0)
    
    # Executar migração
    success = migrate()
    
    # Resultado final
    print_header("RESULTADO")
    if success:
        print_success("Migração concluída com sucesso!")
        print_info("\nPróximos passos:")
        print("  1. Reinicie a aplicação Flask")
        print("  2. Acesse /admin/templates para criar/editar modelos")
        print("  3. Configure a duração de cada etapa dos modelos")
        print("\n")
        sys.exit(0)
    else:
        print_error("Migração falhou!")
        print_info("Verifique os erros acima e tente novamente")
        print("\n")
        sys.exit(1)
