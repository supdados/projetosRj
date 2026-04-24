#!/usr/bin/env python3

from pathlib import Path
import sys
import getpass
from sqlalchemy.exc import IntegrityError, OperationalError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Importa a instância do app e do db, e o modelo User
from app import app
from models import db, User


def create_admin_user():
    """
    Script interativo para criar um novo usuário administrador no banco de dados.
    """
    # Executa dentro do contexto da aplicação Flask para ter acesso ao banco de dados
    with app.app_context():
        print("--- Criação de Usuário Administrador ---")

        try:
            # Verifica a conexão com o banco de dados fazendo uma consulta simples
            db.session.query(User).first()
        except OperationalError as e:
            print("\nERRO: Não foi possível conectar ao banco de dados.")
            print(f"Detalhes: {e}")
            print(
                "Por favor, verifique suas variáveis de ambiente (CLOUD_SQL_CONNECTION_NAME, etc.) e se o banco está acessível."
            )
            return
        except Exception as e:
            print(f"\nOcorreu um erro inesperado ao acessar o banco de dados: {e}")
            return

        # Solicita o nome de usuário (username)
        while True:
            username = input("Digite o nome de usuário (ex: 'admin'): ").strip()
            if username:
                break
            print("O nome de usuário não pode ser vazio.")

        # Verifica se o usuário já existe
        if User.query.filter_by(username=username).first():
            print(f"\nERRO: O usuário '{username}' já existe. Abortando.")
            return

        # Solicita o nome completo
        while True:
            name = input("Digite o nome completo do administrador: ").strip()
            if name:
                break
            print("O nome completo não pode ser vazio.")

        # Solicita a senha de forma segura (não será exibida no terminal)
        while True:
            password = getpass.getpass("Digite a senha do administrador: ")
            if not password:
                print("A senha não pode ser vazia.")
                continue

            password_confirm = getpass.getpass("Confirme a senha: ")
            if password == password_confirm:
                break
            print("\nAs senhas não coincidem. Tente novamente.")

        # Campos opcionais
        orgao = input("Digite o órgão (opcional, pressione Enter para pular): ").strip()

        try:
            # Cria a instância do usuário com os dados fornecidos
            admin_user = User(
                username=username,
                name=name,
                orgao=orgao or None,  # Salva como NULL se a string for vazia
                is_admin=True,  # Define o usuário como administrador
            )

            # Usa o método do modelo para gerar o hash da senha
            admin_user.set_password(password)

            # Adiciona o novo usuário à sessão e salva no banco de dados
            db.session.add(admin_user)
            db.session.commit()

            print(f"\n✅ Usuário administrador '{username}' criado com sucesso!")

        except IntegrityError:
            db.session.rollback()
            print(
                f"\nERRO: O usuário '{username}' já existe (detectado durante a inserção)."
            )
        except Exception as e:
            db.session.rollback()
            print(f"\nOcorreu um erro ao salvar o usuário no banco de dados: {e}")


if __name__ == "__main__":
    create_admin_user()
