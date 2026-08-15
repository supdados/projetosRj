"""Sprint 5.4: um produtor de DDL só.

O schema vem de `alembic upgrade head`. Fora de `tests/` a única chamada de
`db.create_all()` tolerada é a do seed de banco descartável — qualquer outra
reintroduz um segundo produtor de schema e reprova aqui.
"""

from pathlib import Path
import ast

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# seed_fake_data cria schema so em banco descartavel e vazio (guarda no proprio script)
ALLOWED_CREATE_ALL = {"scripts/seed_fake_data.py"}

SCANNED_DIRS = ("routes", "services", "models", "scripts", "migrations", "catalogs")
SCANNED_FILES = ("app.py", "startup.py", "wsgi.py")


def _python_sources() -> list[Path]:
    sources = [
        path
        for directory in SCANNED_DIRS
        for path in (PROJECT_ROOT / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    sources.extend(
        PROJECT_ROOT / name for name in SCANNED_FILES if (PROJECT_ROOT / name).exists()
    )
    return sources


def _calls_create_all(source: str) -> bool:
    """`create_all(...)` como chamada real — docstring/comentário citando não conta."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "create_all":
            return True
    return False


def _create_all_call_sites() -> list[str]:
    """Arquivos (relativos à raiz) que realmente chamam `create_all(...)`."""
    return sorted(
        str(path.relative_to(PROJECT_ROOT))
        for path in _python_sources()
        if _calls_create_all(path.read_text(encoding="utf-8"))
    )


def test_create_all_fora_de_tests_so_no_seed_descartavel():
    assert set(_create_all_call_sites()) == ALLOWED_CREATE_ALL


def test_runner_pre_alembic_nao_ressuscita():
    """`compatible_names` (ix_/uq_) morreu com a baseline — não pode voltar."""
    assert not (PROJECT_ROOT / "scripts/migrations/run_migrations.py").exists()
    assert not (PROJECT_ROOT / "scripts/migrations/legacy_run_migrations.py").exists()

    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _python_sources()
        if "compatible_names" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
