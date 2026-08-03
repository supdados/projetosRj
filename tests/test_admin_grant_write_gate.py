"""Defesa em profundidade: quem pode ESCREVER `is_admin`/`is_super_admin`.

O guard de autorização não pode viver só no endpoint. Este gate varre o fonte e
exige que a atribuição de ``.is_admin`` exista em um único lugar
(``services/admin_grant_policy.apply_admin_flag``) e que ``.is_super_admin``
nunca seja atribuída em Python — a coluna só muda por migração/DB.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]

# Fonte varrido: onde vive a lógica de aplicação. `scripts/` entra apenas na
# checagem de `is_super_admin` (a migração usa SQL cru, nunca atributo Python).
FONTE_APP = ("routes", "services", "models", "app.py", "startup.py")
FONTE_TOTAL = (*FONTE_APP, "scripts", "catalogs")

ARQUIVO_DA_POLITICA = "services/admin_grant_policy.py"

# Construção de `User(is_admin=...)`: congelada no endpoint de criação, que já
# passa por `denial_for_admin_flag_change` antes de instanciar.
BASELINE_KWARG_IS_ADMIN: dict[str, int] = {"routes/api/admin_users.py": 1}

_ESCRITA_IS_ADMIN = re.compile(r"\.is_admin\s*=(?!=)")
_ESCRITA_IS_SUPER_ADMIN = re.compile(r"\.is_super_admin\s*=(?!=)")
_KWARG_IS_ADMIN = re.compile(r"(?<![.\w])is_admin\s*=(?!=)")

_DIRS_IGNORADOS = frozenset(
    {".git", ".venv", "venv", "__pycache__", "node_modules", "frontend", "static"}
)


def _arquivos_py(alvos: tuple[str, ...]) -> Iterator[Path]:
    """Percorre os .py dos alvos (arquivo solto ou diretório) do repositório."""
    for alvo in alvos:
        caminho = REPO_ROOT / alvo
        if caminho.is_file():
            yield caminho
            continue
        for dirpath, dirnames, filenames in os.walk(caminho):
            dirnames[:] = sorted(d for d in dirnames if d not in _DIRS_IGNORADOS)
            for nome in sorted(filenames):
                if nome.endswith(".py"):
                    yield Path(dirpath) / nome


def _ocorrencias(padrao: re.Pattern[str], alvos: tuple[str, ...]) -> list[str]:
    """Lista ``caminho:linha`` de cada casamento do padrão no fonte."""
    achados: list[str] = []
    for path in _arquivos_py(alvos):
        relativo = path.relative_to(REPO_ROOT).as_posix()
        for numero, linha in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if padrao.search(linha):
                achados.append(f"{relativo}:{numero}")
    return achados


def _contagem_por_arquivo(
    padrao: re.Pattern[str], alvos: tuple[str, ...]
) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for ocorrencia in _ocorrencias(padrao, alvos):
        relativo = ocorrencia.rsplit(":", 1)[0]
        contagem[relativo] = contagem.get(relativo, 0) + 1
    return contagem


def test_apenas_a_politica_atribui_is_admin():
    fora = [
        ocorrencia
        for ocorrencia in _ocorrencias(_ESCRITA_IS_ADMIN, FONTE_APP)
        if not ocorrencia.startswith(ARQUIVO_DA_POLITICA + ":")
    ]

    assert fora == [], (
        "Escrita de `.is_admin` fora de "
        f"{ARQUIVO_DA_POLITICA} (use apply_admin_flag): {fora}"
    )


def test_a_politica_realmente_atribui_a_flag():
    """Se a única escrita sumisse, o teste acima passaria vazio por acidente."""
    assert _ocorrencias(_ESCRITA_IS_ADMIN, (ARQUIVO_DA_POLITICA,))


def test_nenhum_codigo_atribui_is_super_admin():
    achados = _ocorrencias(_ESCRITA_IS_SUPER_ADMIN, FONTE_TOTAL)

    assert achados == [], (
        "`is_super_admin` só muda por migração/DB; atribuição encontrada em: "
        f"{achados}"
    )


def test_kwarg_is_admin_esta_congelado_na_baseline():
    contagem = _contagem_por_arquivo(_KWARG_IS_ADMIN, ("routes", "services"))
    excedentes = {
        relativo: usos
        for relativo, usos in contagem.items()
        if usos > BASELINE_KWARG_IS_ADMIN.get(relativo, 0)
    }

    assert excedentes == {}, (
        "Construção com `is_admin=` fora da baseline "
        f"{BASELINE_KWARG_IS_ADMIN}: {excedentes}"
    )


def test_endpoint_admin_usa_a_politica():
    fonte = (REPO_ROOT / "routes" / "api" / "admin_users.py").read_text(
        encoding="utf-8"
    )

    assert "apply_admin_flag" in fonte
    assert "from services.admin_grant_policy import" in fonte
