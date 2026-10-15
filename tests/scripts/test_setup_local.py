"""Instalação local (`scripts/dev/setup_local.py`): partes puras e idempotência."""

from __future__ import annotations

from scripts.dev.setup_local import (
    ENV_LOCAL_OVERRIDES,
    node_version_problem,
    parse_node_version,
    python_version_problem,
    render_local_env,
    write_local_env,
)

TEMPLATE = (
    "# comentário\n"
    "SECRET_KEY=\n"
    "FLASK_DEBUG=0\n"
    "# GOVBR_OIDC_ENABLED=1\n"
    "DATABASE_URL=\n"
)


def _valores(env_text: str) -> dict[str, str]:
    pares = (
        linha.split("=", 1)
        for linha in env_text.splitlines()
        if linha and not linha.startswith("#")
    )
    return dict(pares)


def test_render_local_env_troca_valores_do_perfil_local():
    valores = _valores(render_local_env(TEMPLATE, "chave-gerada"))

    assert valores["SECRET_KEY"] == "chave-gerada"
    assert valores["FLASK_DEBUG"] == "1"
    assert valores["DATABASE_URL"] == ""


def test_render_local_env_acrescenta_chaves_ausentes_e_preserva_comentarios():
    texto = render_local_env(TEMPLATE, "x")
    valores = _valores(texto)

    assert "# GOVBR_OIDC_ENABLED=1" in texto
    for chave, valor in ENV_LOCAL_OVERRIDES.items():
        assert valores[chave] == valor


def test_write_local_env_nao_sobrescreve(tmp_path):
    (tmp_path / ".env.example").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET_KEY=minha\n", encoding="utf-8")

    assert write_local_env(tmp_path) is False
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET_KEY=minha\n"


def test_write_local_env_gera_secret_key_aleatoria(tmp_path):
    (tmp_path / ".env.example").write_text(TEMPLATE, encoding="utf-8")

    assert write_local_env(tmp_path) is True
    secret = _valores((tmp_path / ".env").read_text(encoding="utf-8"))["SECRET_KEY"]
    assert len(secret) == 64


def test_parse_node_version():
    assert parse_node_version("v22.12.0\n") == (22, 12)
    assert parse_node_version("lixo") is None


def test_node_version_problem():
    assert node_version_problem("v24.1.0") is None
    assert node_version_problem("v22.12.0") is None
    assert "22.12" in node_version_problem("v20.19.2")


def test_python_version_problem():
    assert python_version_problem((3, 12, 0)) is None
    assert python_version_problem((3, 14, 1)) is None
    assert "3.11.9" in python_version_problem((3, 11, 9))
