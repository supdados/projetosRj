#!/usr/bin/env python3
"""Instalação local do ProjetosRJ para quem chega pela primeira vez.

Pré-requisito: venv ativo com as dependências instaladas
(`pip install -r requirements -r requirements-dev.txt`) e Node/npm no PATH.

Uso:
    python scripts/dev/setup_local.py                  # pergunta usuário/senha do admin
    python scripts/dev/setup_local.py --sem-frontend   # pula npm ci + build
    PROJETOSRJ_ADMIN_SENHA='SenhaForte12' python scripts/dev/setup_local.py \\
        --admin-usuario admin                          # sem perguntas (automação)

O que faz: cria o `.env` (SECRET_KEY gerada, cookie sem HTTPS, TODAS as
integrações externas desligadas — Gov.br, Google Calendar, watsonx, SIORG,
chatbot), aplica as migrações num SQLite em `instance/`, sincroniza o
catálogo de objetivos, cria o primeiro admin (login local) e gera a SPA.

Pode rodar de novo sem estragar nada: não sobrescreve `.env` existente,
`flask db upgrade` e o catálogo são no-op num banco em dia e o admin só é
criado se ainda não houver nenhum.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.password_policy import validate_password_strength

PYTHON_MINIMO = (3, 12)
NODE_MINIMO = (22, 12)
SENHA_ENV_VAR = "PROJETOSRJ_ADMIN_SENHA"

# Perfil de dev local: nada externo ligado e cookie aceito em http://.
ENV_LOCAL_OVERRIDES: dict[str, str] = {
    "FLASK_DEBUG": "1",
    "SESSION_COOKIE_SECURE": "0",
    "GOVBR_OIDC_ENABLED": "0",
    "GOOGLE_CALENDAR_ENABLED": "0",
    "WATSONX_ENABLED": "0",
    "SIORG_ENABLED": "0",
    "CHATBOT_ENABLED": "0",
    "CONVITES_HABILITADOS": "0",
}

_LINHA_ENV = re.compile(r"^([A-Z][A-Z0-9_]*)=")


def render_local_env(template: str, secret_key: str) -> str:
    """`.env` de dev a partir do `.env.example`: troca os valores do perfil local.

    Linhas comentadas ficam como estão; chave do perfil ausente no template é
    acrescentada no fim. Ex.: ``render_local_env("SECRET_KEY=\\n", "abc")``
    começa com ``"SECRET_KEY=abc\\n"``.
    """
    valores = {"SECRET_KEY": secret_key, **ENV_LOCAL_OVERRIDES}
    pendentes = dict(valores)
    linhas = []
    for linha in template.splitlines():
        chave = _LINHA_ENV.match(linha)
        if chave and chave.group(1) in valores:
            linha = f"{chave.group(1)}={valores[chave.group(1)]}"
            pendentes.pop(chave.group(1), None)
        linhas.append(linha)
    linhas.extend(f"{chave}={valor}" for chave, valor in pendentes.items())
    return "\n".join(linhas) + "\n"


def write_local_env(root: Path) -> bool:
    """Cria `root/.env` a partir do `.env.example`; False se já existia (intocado)."""
    destino = root / ".env"
    if destino.exists():
        return False
    template = (root / ".env.example").read_text(encoding="utf-8")
    destino.write_text(
        render_local_env(template, secrets.token_hex(32)), encoding="utf-8"
    )
    return True


def parse_node_version(raw: str) -> tuple[int, int] | None:
    """``"v22.12.0"`` → ``(22, 12)``; None se a saída do `node -v` não bater."""
    achado = re.match(r"v?(\d+)\.(\d+)", raw.strip())
    if not achado:
        return None
    return int(achado.group(1)), int(achado.group(2))


def python_version_problem(version: Sequence[int]) -> str | None:
    """Mensagem se o Python for anterior ao mínimo (o CI roda 3.12)."""
    if tuple(version[:2]) >= PYTHON_MINIMO:
        return None
    atual = ".".join(str(parte) for parte in version[:3])
    return f"Python {atual} encontrado; esperado >= 3.12."


def node_version_problem(raw: str) -> str | None:
    """Aviso (não bloqueia) se o Node for anterior a 22.12 (mínimo do vitest)."""
    versao = parse_node_version(raw)
    if versao is None:
        return f"Não entendi a versão do Node ({raw.strip()!r}); esperado >= 22.12."
    if versao >= NODE_MINIMO:
        return None
    return (
        f"Node {raw.strip()} encontrado; recomendado >= 22.12 "
        "(o build funciona, os testes do frontend pedem 22.12+)."
    )


def _etapa(titulo: str) -> None:
    print(f"\n==> {titulo}", flush=True)


def _rodar(cmd: Sequence[str], cwd: Path) -> None:
    """Roda um comando mostrando a saída; aborta a instalação se falhar."""
    print("    $ " + " ".join(cmd), flush=True)
    subprocess.run(list(cmd), cwd=cwd, check=True)


def _migrar_banco(root: Path) -> None:
    _etapa("Aplicando migrações (flask db upgrade)")
    _rodar([sys.executable, "-m", "flask", "--app", "app", "db", "upgrade"], root)


def _sincronizar_catalogo(root: Path) -> None:
    _etapa("Sincronizando catálogo de objetivos")
    _rodar([sys.executable, "scripts/catalog/sync_objectives_catalog.py"], root)


def _perguntar_senha() -> str:
    """Pede a senha (sem eco) até passar na política de força do app."""
    while True:
        senha = getpass.getpass("Senha do admin (mín. 8 caracteres): ")
        erro = validate_password_strength(senha)
        if erro is None:
            return senha
        print(f"    {erro}")


def _dados_do_admin(args: argparse.Namespace) -> tuple[str, str, str]:
    """(usuário, nome, senha) por flag/env ou perguntando no terminal."""
    senha = os.environ.get(SENHA_ENV_VAR, "")
    if args.admin_usuario and senha:
        return args.admin_usuario, args.admin_nome, senha
    if not sys.stdin.isatty():
        raise SystemExit(
            f"Sem terminal para perguntar: use --admin-usuario e {SENHA_ENV_VAR}."
        )
    usuario = args.admin_usuario or input("Usuário do admin [admin]: ").strip()
    return usuario or "admin", args.admin_nome, senha or _perguntar_senha()


def _criar_admin(args: argparse.Namespace) -> str | None:
    """Cria o primeiro admin; devolve o login criado ou None se já havia um."""
    _etapa("Primeiro usuário administrador (login local)")
    # Import tardio: o app lê o `.env` no import, e ele só existe a partir daqui.
    from scripts.admin.gerar_senha import (
        AdminInvalido,
        NovoAdmin,
        app,
        criar_admin,
        existe_admin_ativo,
    )

    with app.app_context():
        if existe_admin_ativo():
            print("    Já existe administrador — nada a fazer.")
            return None
        usuario, nome, senha = _dados_do_admin(args)
        try:
            criar_admin(NovoAdmin(usuario, nome, senha))
        except AdminInvalido as exc:
            raise SystemExit(f"Admin recusado: {exc}") from exc
    print(f"    Admin '{usuario}' criado.")
    return usuario


def _gerar_frontend(root: Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        print("    AVISO: npm não encontrado — instale o Node 22+ e rode")
        print("    `cd frontend && npm ci && npm run build` antes de abrir o app.")
        return
    node = shutil.which("node")
    if node:
        saida = subprocess.run([node, "-v"], capture_output=True, text=True).stdout
        aviso = node_version_problem(saida)
        if aviso:
            print(f"    AVISO: {aviso}")
    _etapa("Instalando e gerando o frontend (npm ci + npm run build)")
    _rodar([npm, "ci"], root / "frontend")
    _rodar([npm, "run", "build"], root / "frontend")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Instala o ProjetosRJ para desenvolvimento local (SQLite, sem integrações)."
    )
    parser.add_argument(
        "--sem-frontend", action="store_true", help="Pula npm ci + build."
    )
    parser.add_argument("--admin-usuario", default=None, help="Login do admin.")
    parser.add_argument("--admin-nome", default="Administrador")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    problema = python_version_problem(sys.version_info)
    if problema:
        print(f"ERRO: {problema}")
        return 1

    _etapa("Arquivo .env")
    if write_local_env(PROJECT_ROOT):
        print("    .env criado (SECRET_KEY gerada; integrações externas desligadas).")
    else:
        print("    .env já existe — mantido como está.")

    _migrar_banco(PROJECT_ROOT)
    _sincronizar_catalogo(PROJECT_ROOT)
    admin = _criar_admin(args)
    if not args.sem_frontend:
        _gerar_frontend(PROJECT_ROOT)

    print("\nPronto. Para subir:  python app.py")
    print("Depois abra:         http://localhost:5002/login")
    if admin:
        print(f"Entre com:           {admin} / (a senha que você definiu)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
