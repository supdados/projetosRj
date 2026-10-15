#!/usr/bin/env python3
"""Cria um usuário administrador com login local (não depende do Gov.br).

Uso interativo:
    python scripts/admin/gerar_senha.py

Uso não interativo (instalação automatizada, ex.: scripts/dev/setup_local.py):
    PROJETOSRJ_ADMIN_SENHA='SenhaForte12' python scripts/admin/gerar_senha.py \\
        --usuario admin --nome "Administrador"

A senha vem de variável de ambiente, nunca de argumento: argv fica no
histórico do shell e aparece no `ps` para outros usuários da máquina.
"""

import argparse
import getpass
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError, OperationalError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Importa a instância do app e do db, e o modelo User
from app import app
from models import db, User
from scripts.migrations.elect_super_admin import (
    elect_initial_super_admin,
    existe_admin_ativo,
)
from services.password_policy import validate_password_strength

SENHA_ENV_VAR = "PROJETOSRJ_ADMIN_SENHA"


class AdminInvalido(ValueError):
    """Dados do novo admin recusados (usuário já existe ou senha fraca)."""


@dataclass(frozen=True)
class NovoAdmin:
    username: str
    name: str
    password: str
    orgao: str | None = None


def criar_admin(novo: NovoAdmin) -> bool:
    """Grava o admin e elege o super admin inicial; True se ele virou o principal.

    Requer app context. Erra com ``AdminInvalido`` (usuário existente, senha
    fraca) e ``IntegrityError`` (corrida na inserção). Ex.:
    ``criar_admin(NovoAdmin("admin", "Admin", "SenhaForte12"))`` → ``True``.
    """
    erro_senha = validate_password_strength(novo.password)
    if erro_senha:
        raise AdminInvalido(erro_senha)
    if User.query.filter_by(username=novo.username).first():
        raise AdminInvalido(f"O usuário '{novo.username}' já existe.")
    admin_user = User(
        username=novo.username,
        name=novo.name,
        orgao=novo.orgao or None,  # Salva como NULL se a string for vazia
        is_admin=True,
    )
    admin_user.set_password(novo.password)
    db.session.add(admin_user)
    db.session.flush()
    # Numa base nova ninguém é super admin, e sem super admin nenhum
    # admin consegue conceder is_admin até um restart rodar a eleição.
    eleito = elect_initial_super_admin()
    db.session.commit()
    return eleito == admin_user.id


def _banco_acessivel() -> bool:
    """Consulta simples para falhar cedo, com dica, se o banco não responde."""
    try:
        db.session.query(User).first()
    except OperationalError as e:
        print("\nERRO: Não foi possível conectar ao banco de dados.")
        print(f"Detalhes: {e}")
        print(
            "Verifique DATABASE_URL/DB_* no .env (vazio = SQLite em instance/) "
            "e se `flask db upgrade` já foi rodado."
        )
        return False
    except Exception as e:
        print(f"\nOcorreu um erro inesperado ao acessar o banco de dados: {e}")
        return False
    return True


def _print_sucesso(username: str, principal: bool) -> None:
    print(f"\n✅ Usuário administrador '{username}' criado com sucesso!")
    if principal:
        print("   ↳ Definido como administrador principal do sistema.")


def _perguntar_obrigatorio(prompt: str, erro: str) -> str:
    while True:
        valor = input(prompt).strip()
        if valor:
            return valor
        print(erro)


def _perguntar_senha() -> str:
    """Pede a senha duas vezes (sem eco) até bater e passar na política."""
    while True:
        password = getpass.getpass("Digite a senha do administrador: ")
        erro = validate_password_strength(password)
        if erro:
            print(erro)
            continue
        if password == getpass.getpass("Confirme a senha: "):
            return password
        print("\nAs senhas não coincidem. Tente novamente.")


def _gravar(novo: NovoAdmin) -> bool:
    """Chama ``criar_admin`` traduzindo falhas em mensagem; True se gravou."""
    try:
        principal = criar_admin(novo)
    except AdminInvalido as exc:
        db.session.rollback()
        print(f"\nERRO: {exc}")
        return False
    except IntegrityError:
        db.session.rollback()
        print(
            f"\nERRO: O usuário '{novo.username}' já existe (detectado durante a inserção)."
        )
        return False
    except Exception as e:
        db.session.rollback()
        print(f"\nOcorreu um erro ao salvar o usuário no banco de dados: {e}")
        return False
    _print_sucesso(novo.username, principal)
    return True


def create_admin_user():
    """
    Script interativo para criar um novo usuário administrador no banco de dados.
    """
    # Executa dentro do contexto da aplicação Flask para ter acesso ao banco de dados
    with app.app_context():
        print("--- Criação de Usuário Administrador ---")
        if not _banco_acessivel():
            return

        username = _perguntar_obrigatorio(
            "Digite o nome de usuário (ex: 'admin'): ",
            "O nome de usuário não pode ser vazio.",
        )
        if User.query.filter_by(username=username).first():
            print(f"\nERRO: O usuário '{username}' já existe. Abortando.")
            return

        name = _perguntar_obrigatorio(
            "Digite o nome completo do administrador: ",
            "O nome completo não pode ser vazio.",
        )
        password = _perguntar_senha()
        orgao = input("Digite o órgão (opcional, pressione Enter para pular): ").strip()
        _gravar(NovoAdmin(username, name, password, orgao or None))


def criar_admin_por_argumentos(args: argparse.Namespace) -> int:
    """Modo não interativo: senha em ``PROJETOSRJ_ADMIN_SENHA``; 0 = criado."""
    senha = os.environ.get(SENHA_ENV_VAR, "")
    if not senha:
        print(f"ERRO: defina a senha na variável de ambiente {SENHA_ENV_VAR}.")
        return 2
    with app.app_context():
        if not _banco_acessivel():
            return 1
        novo = NovoAdmin(args.usuario, args.nome, senha, args.orgao)
        return 0 if _gravar(novo) else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria um usuário administrador com login local."
    )
    parser.add_argument(
        "--usuario", help="Login do admin; informado = modo não interativo."
    )
    parser.add_argument("--nome", default="Administrador", help="Nome completo.")
    parser.add_argument("--orgao", default=None, help="Órgão (opcional).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.usuario:
        return criar_admin_por_argumentos(args)
    create_admin_user()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
