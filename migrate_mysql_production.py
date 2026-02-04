#!/usr/bin/env python3
"""
Script para adicionar novos campos ao modelo Project no MySQL de Produção
Execute este script no ambiente Linux com MySQL
"""

import pymysql
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

def get_db_config():
    """Retorna configuração do banco de dados MySQL"""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME', 'projetosRj'),
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }

def column_exists(cursor, table_name, column_name):
    """Verifica se uma coluna existe na tabela"""
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = %s 
        AND COLUMN_NAME = %s
    """, (table_name, column_name))
    result = cursor.fetchone()
    return result['count'] > 0

def migrate_database():
    """Adiciona as novas colunas ao banco de dados MySQL"""
    
    db_config = get_db_config()
    
    print("="*70)
    print("  Migração MySQL - Novos Campos do Projeto")
    print("="*70)
    print(f"\n📊 Banco de dados: {db_config['database']}")
    print(f"🖥️  Host: {db_config['host']}")
    print(f"👤 Usuário: {db_config['user']}")
    print()
    
    try:
        # Conectar ao banco
        print("🔌 Conectando ao MySQL...")
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()
        print("✓ Conexão estabelecida com sucesso!")
        print()
        
        # Lista de colunas a adicionar
        # Formato: (nome_coluna, tipo_mysql, comentário)
        columns_to_add = [
            ("special_project", "VARCHAR(20) NULL", "Projeto especial: ABEP ou TCE"),
            ("sei_process", "VARCHAR(50) NULL", "Número do processo SEI"),
            ("short_description", "TEXT NULL", "Descrição curta do projeto"),
            ("delivery_type", "VARCHAR(50) NULL", "Tipo de entrega do projeto"),
            ("github_link", "VARCHAR(500) NULL", "Link do repositório Github"),
            ("documentation_link", "VARCHAR(500) NULL", "Link da documentação")
        ]
        
        print("📝 Verificando e adicionando colunas...")
        print()
        
        added_count = 0
        skipped_count = 0
        
        for column_name, column_type, description in columns_to_add:
            if column_exists(cursor, 'project', column_name):
                print(f"  ⏭️  {column_name:25} → Já existe (ignorado)")
                skipped_count += 1
            else:
                try:
                    sql = f"ALTER TABLE project ADD COLUMN {column_name} {column_type} COMMENT '{description}'"
                    cursor.execute(sql)
                    connection.commit()
                    print(f"  ✅ {column_name:25} → Adicionada com sucesso")
                    added_count += 1
                except Exception as e:
                    print(f"  ❌ {column_name:25} → Erro: {str(e)}")
                    connection.rollback()
        
        print()
        print("="*70)
        print("📊 Resumo da Migração:")
        print("="*70)
        print(f"  ✅ Colunas adicionadas: {added_count}")
        print(f"  ⏭️  Colunas já existentes: {skipped_count}")
        print(f"  📝 Total verificadas: {len(columns_to_add)}")
        print("="*70)
        
        if added_count > 0:
            print()
            print("✓ Migração concluída com sucesso!")
            print()
            print("📋 Novas colunas disponíveis:")
            for column_name, _, description in columns_to_add:
                if not column_exists(cursor, 'project', column_name):
                    continue
                print(f"   • {column_name}: {description}")
        else:
            print()
            print("ℹ️  Nenhuma alteração necessária - todas as colunas já existem.")
        
        cursor.close()
        connection.close()
        print()
        print("🔌 Conexão fechada.")
        
        return True
        
    except pymysql.Error as e:
        print()
        print("="*70)
        print(f"❌ ERRO DE BANCO DE DADOS: {e}")
        print("="*70)
        print()
        print("💡 Dicas de solução:")
        print("   1. Verifique as credenciais no arquivo .env")
        print("   2. Certifique-se de que o MySQL está rodando")
        print("   3. Verifique se o usuário tem permissão para ALTER TABLE")
        print("   4. Confirme o nome do banco de dados")
        print()
        return False
        
    except Exception as e:
        print()
        print("="*70)
        print(f"❌ ERRO INESPERADO: {e}")
        print("="*70)
        return False

def show_env_help():
    """Mostra instruções sobre configuração do .env"""
    print()
    print("="*70)
    print("  Configuração do arquivo .env")
    print("="*70)
    print()
    print("Certifique-se de que o arquivo .env contém:")
    print()
    print("  DB_HOST=localhost          # ou IP do servidor MySQL")
    print("  DB_USER=seu_usuario        # usuário do MySQL")
    print("  DB_PASSWORD=sua_senha      # senha do MySQL")
    print("  DB_NAME=projetosRj         # nome do banco de dados")
    print()
    print("="*70)

if __name__ == '__main__':
    print()
    
    # Verificar se o arquivo .env existe
    if not os.path.exists('.env'):
        print("⚠️  AVISO: Arquivo .env não encontrado!")
        show_env_help()
        print()
        input("Pressione ENTER para continuar mesmo assim ou CTRL+C para cancelar...")
        print()
    
    # Executar migração
    success = migrate_database()
    
    if not success:
        show_env_help()
        exit(1)
    
    print()
    print("="*70)
    print("  ✅ Script concluído!")
    print("="*70)
    print()
