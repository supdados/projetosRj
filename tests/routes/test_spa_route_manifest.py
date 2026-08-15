"""Round-trip do manifesto de rotas da SPA (static/spa/routes.json).

A verdade são os FONTES ``frontend/src/routes/(app)/**`` (roda sem build): o
teste deriva deles o manifesto esperado e o compara com o emitido por
``frontend/scripts/emit-routes-manifest.js`` quando o build existe. Também
garante que nenhuma URL viva da lista antiga (ex-_MIGRATED_EXACT_PATHS) sumiu
do matcher.
"""

from __future__ import annotations

import json
import os

import pytest

import routes.spa as spa_module

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_APP_ROUTES_DIR = os.path.join(_REPO_ROOT, "frontend", "src", "routes", "(app)")

# Ex-_MIGRATED_EXACT_PATHS (routes/spa.py antes do manifesto), MENOS "admin":
# nunca teve +page.svelte — servia a shell com o 404 do SvelteKit em HTTP 200.
_LEGACY_EXACT_PATHS = frozenset(
    {
        "projetos",
        "projetos/pendentes",
        "admin/usuarios",
        "admin/usuarios/novo",
        "admin/orgaos",
        "admin/templates",
        "busca",
        "colecoes",
        "dashboard",
        "tarefas",
        "calendarios",
    }
)
_LEGACY_DYNAMIC_PATTERNS = frozenset(
    {
        r"projetos/\d+",
        r"projetos/\d+/historico",
        r"admin/usuarios/\d+",
        r"colecoes/\d+",
    }
)


def _derive_manifest_from_sources() -> tuple[set[str], set[str]]:
    """Replica emit-routes-manifest.js: (exatos, padrões dinâmicos) dos fontes."""
    exact: set[str] = set()
    dynamic: set[str] = set()
    for dirpath, _dirnames, filenames in os.walk(_APP_ROUTES_DIR):
        if "+page.svelte" not in filenames:
            continue
        relative = os.path.relpath(dirpath, _APP_ROUTES_DIR)
        segments = [s for s in relative.split(os.sep) if not s.startswith("(")]
        if not segments or relative == ".":
            continue
        path = "/".join(segments)
        if "[" in path:
            dynamic.add(_dynamic_pattern(path))
        else:
            exact.add(path)
    return exact, dynamic


def _dynamic_pattern(path: str) -> str:
    """Converte segmentos ``[param]`` em ``\\d+`` (ids numéricos)."""
    import re

    return re.sub(r"\[[^\]]+\]", r"\\d+", path)


def test_app_routes_sources_exist():
    assert os.path.isdir(_APP_ROUTES_DIR), _APP_ROUTES_DIR


def test_no_live_url_left_matcher():
    """Todo path da lista antiga (com página real) segue coberto pelos fontes."""
    exact, dynamic = _derive_manifest_from_sources()
    assert _LEGACY_EXACT_PATHS <= exact
    assert _LEGACY_DYNAMIC_PATTERNS <= dynamic


def test_admin_root_has_no_source_page():
    """``/admin`` não tem +page.svelte — deve ficar fora do matcher (404 limpo)."""
    exact, _dynamic = _derive_manifest_from_sources()
    assert "admin" not in exact


@pytest.mark.skipif(
    not os.path.exists(spa_module._ROUTE_MANIFEST_PATH),
    reason="requer manifesto do build (npm run build em frontend/)",
)
def test_manifest_round_trips_with_sources():
    """routes.json ⊇⊆ fontes: nada a mais, nada a menos."""
    with open(spa_module._ROUTE_MANIFEST_PATH, encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    exact, dynamic = _derive_manifest_from_sources()
    assert set(manifest["exact"]) == exact
    assert set(manifest["dynamic"]) == dynamic


def test_missing_manifest_means_no_migrated_paths(monkeypatch):
    """Fallback explícito: sem routes.json, nenhum path é migrado (e não cacheia
    a ausência — um build posterior passa a valer sem restart)."""
    monkeypatch.setattr(spa_module, "_ROUTE_MANIFEST_PATH", "/nonexistent/routes.json")
    monkeypatch.setattr(spa_module, "_manifest_cache", None)
    assert spa_module._is_migrated_spa_path("projetos") is False
    assert spa_module._manifest_cache is None


def test_manifest_recarrega_apos_rebuild_por_mtime(monkeypatch, tmp_path):
    """Rebuild que reescreve o routes.json vale sem restart (cache por mtime)."""
    manifest_path = tmp_path / "routes.json"
    manifest_path.write_text('{"exact": ["projetos"], "dynamic": []}')
    monkeypatch.setattr(spa_module, "_ROUTE_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(spa_module, "_manifest_cache", None)
    assert spa_module._is_migrated_spa_path("relatorios") is False

    manifest_path.write_text('{"exact": ["projetos", "relatorios"], "dynamic": []}')
    os.utime(manifest_path, (manifest_path.stat().st_atime, manifest_path.stat().st_mtime + 2))
    assert spa_module._is_migrated_spa_path("relatorios") is True


def test_manifest_corrompido_vira_vazio_e_nao_500(monkeypatch, tmp_path):
    """JSON parcial na janela do build: catch-all fica inerte, sem estourar."""
    manifest_path = tmp_path / "routes.json"
    manifest_path.write_text('{"exact": ["proj')
    monkeypatch.setattr(spa_module, "_ROUTE_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(spa_module, "_manifest_cache", None)
    assert spa_module._is_migrated_spa_path("projetos") is False


@pytest.mark.skipif(
    not os.path.exists(spa_module._ROUTE_MANIFEST_PATH),
    reason="requer manifesto do build (npm run build em frontend/)",
)
def test_manifest_loader_matches_exact_and_dynamic(monkeypatch):
    """Loader compila o manifesto real: exato casa, dinâmico exige \\d+ inteiro."""
    monkeypatch.setattr(spa_module, "_manifest_cache", None)
    assert spa_module._is_migrated_spa_path("projetos") is True
    assert spa_module._is_migrated_spa_path("projetos/123") is True
    assert spa_module._is_migrated_spa_path("projetos/abc") is False
    assert spa_module._is_migrated_spa_path("admin") is False
