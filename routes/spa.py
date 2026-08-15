"""Serve a SPA SvelteKit (CSR) nos PATHS NATIVOS, com deep-link e F5 robustos.

ABORDAGEM
---------
1) ``frontend/svelte.config.js`` usa ``paths.base = ''`` (RAIZ). O roteador
   client-side casa com os PATHS NATIVOS das telas migradas (``/dashboard``,
   ``/projetos``, ``/tarefas``, ``/admin/*``, ``/busca``, ``/calendarios``...).
   Com ``base=''`` o bootstrap referencia os assets em ``/_app/...`` (raiz).
2) Os ASSETS ficam fisicamente em ``static/spa/_app/`` (adapter-static); a rota
   ``/_app/<path>`` faz a ponte (arquivos imutaveis, versionados por hash).
3) O SHELL e FONTE UNICA: ``frontend/src/app.html``. O ``npm run build`` emite
   ``static/spa/index.html`` (ja com o placeholder ``%CSP_NONCE%`` nas tags
   inline via ``scripts/inject-csp-nonce.js``) e ``_render_spa()`` serve esse
   arquivo substituindo os placeholders em runtime — ``%CSP_NONCE%`` (nonce da
   CSP), ``%CSRF_TOKEN%`` (token da sessao p/ ``X-CSRFToken`` do client.ts) e
   ``%CHATBOT_BASE_URL%`` (vazio = chatbot desligado). NADA de template Jinja
   nem parsing de HTML por regex: o HTML do bundle vai integro para o cliente.
4) O MATCHER vem do BUILD: ``scripts/emit-routes-manifest.js`` varre
   ``frontend/src/routes/(app)/**`` e emite ``static/spa/routes.json``
   (``exact`` + ``dynamic``, com ``[param]`` -> ``\\d+``). O catch-all
   ``/<path:spa_path>`` (rank MENOR que rotas estaticas — Werkzeug prioriza
   estaticas — entao so casa o que nenhuma rota Flask atendeu) serve a shell
   apenas nos paths do manifesto; qualquer outro path -> 404 limpo do Flask.
   Ex.: ``/admin`` NAO tem ``+page.svelte`` — fica fora do manifesto e responde
   404 (antes servia a shell com o 404 do SvelteKit em HTTP 200).

CLONE LIMPO (sem ``npm run build``)
-----------------------------------
``static/spa/`` e gitignored: sem build nao existem ``index.html`` nem
``routes.json``. O catch-all responde 404 (manifesto ausente = nenhum path
migrado) e as rotas KEEP-ENDPOINT (``/dashboard``, ``/tarefas``,
``/calendarios``) respondem 503 com instrucao explicita de rodar o build.
As telas de auth (``templates/auth/*``, ``base.html``) nao dependem do bundle.

ESTADO ATUAL
------------
Migracao Jinja->SPA COMPLETA. Deep-links legados ``/projects`` e
``/project/<id>`` sao redirect 302 -> ``/projetos`` e ``/projetos/<id>``
(KEEP-ENDPOINT). ``/dashboard``, ``/tarefas`` e ``/calendarios`` seguem como
rotas estaticas KEEP-ENDPOINT servindo ``_render_spa()`` (prioridade sobre o
catch-all); tambem constam no manifesto como defesa em profundidade.

EXCLUSOES (nunca SPA): ``/api/*``, ``/webhook``, ``/calendar/oauth/*``,
``/auth/*``, ``/login``, ``/logout``, ``/static/*``, ``/favicon.ico``,
``/setup_db``, ``/_app/*`` e ``/spa`` — reserva casa por SEGMENTO completo
(``api`` bloqueia ``/api`` e ``/api/...``, nao ``/apiario``).

A funcao e anexada ao ``main_bp`` UNICO; NAO criamos blueprint novo, para
preservar os ``url_for("main.xxx")`` existentes.
"""

from __future__ import annotations

import json
import os
import re
from typing import NamedTuple

from flask import abort, current_app, g, has_app_context, send_from_directory
from flask_wtf.csrf import generate_csrf
from markupsafe import escape

from .blueprint import main_bp

# Diretorio do bundle buildado (adapter-static -> static/spa/).
_BUNDLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "spa",
)
_BUNDLE_INDEX_PATH = os.path.join(_BUNDLE_DIR, "index.html")
_ROUTE_MANIFEST_PATH = os.path.join(_BUNDLE_DIR, "routes.json")
# Assets imutaveis do SvelteKit; com base='' o cliente os pede em /_app/...
_BUNDLE_APP_DIR = os.path.join(_BUNDLE_DIR, "_app")

_MISSING_BUNDLE_HINT = (
    "Bundle da SPA ausente (static/spa/index.html): rode 'npm run build' em frontend/."
)

# Segmentos que NUNCA sao servidos como SPA, mesmo via catch-all. Defesa em
# profundidade alem das rotas estaticas dedicadas (api/auth/login/...).
_RESERVED_SUBPATH_PREFIXES = (
    "api",
    "webhook",
    "calendar/oauth",
    "auth",
    "login",
    "logout",
    "favicon.ico",
    "setup_db",
    "static",
    "_app",
    "spa",
)


class SpaRouteManifest(NamedTuple):
    """Paths migrados emitidos pelo build (static/spa/routes.json)."""

    exact: frozenset[str]
    dynamic: tuple[re.Pattern[str], ...]


_EMPTY_MANIFEST = SpaRouteManifest(exact=frozenset(), dynamic=())
_manifest_cache: tuple[float, SpaRouteManifest] | None = None


def _read_route_manifest(manifest_path: str) -> SpaRouteManifest:
    """Le e compila o routes.json emitido pelo build (emit-routes-manifest.js).

    Args:
        manifest_path: Caminho absoluto do routes.json.

    Returns:
        Manifesto compilado; vazio (nenhum path migrado) quando o arquivo nao
        existe (clone sem ``npm run build``) ou esta ilegivel — um JSON parcial
        na janela do build nao pode derrubar todos os paths do catch-all.
    """
    try:
        with open(manifest_path, encoding="utf-8") as manifest_file:
            data = json.load(manifest_file)
    except FileNotFoundError:
        _log_manifest_problem(manifest_path, "ausente")
        return _EMPTY_MANIFEST
    except (OSError, json.JSONDecodeError, re.error) as exc:
        _log_manifest_problem(manifest_path, f"ilegivel ({exc})")
        return _EMPTY_MANIFEST
    return SpaRouteManifest(
        exact=frozenset(data.get("exact", [])),
        dynamic=tuple(re.compile(pattern) for pattern in data.get("dynamic", [])),
    )


def _log_manifest_problem(manifest_path: str, motivo: str) -> None:
    """Avisa que o catch-all esta inerte (fora de app context silencia)."""
    if has_app_context():
        current_app.logger.warning(
            "routes.json %s em %s — nenhum path migrado; rode 'npm run build'.",
            motivo,
            manifest_path,
        )


def _load_route_manifest() -> SpaRouteManifest:
    """Devolve o manifesto cacheado por mtime: rebuild vale sem reiniciar."""
    global _manifest_cache
    try:
        mtime = os.path.getmtime(_ROUTE_MANIFEST_PATH)
    except OSError:
        _log_manifest_problem(_ROUTE_MANIFEST_PATH, "ausente")
        return _EMPTY_MANIFEST
    if _manifest_cache is None or _manifest_cache[0] != mtime:
        _manifest_cache = (mtime, _read_route_manifest(_ROUTE_MANIFEST_PATH))
    return _manifest_cache[1]


def _is_migrated_spa_path(normalized: str) -> bool:
    """Indica se ``normalized`` (sem barra inicial) e um path de tela migrada."""
    manifest = _load_route_manifest()
    if normalized in manifest.exact:
        return True
    return any(pattern.fullmatch(normalized) for pattern in manifest.dynamic)


def _is_reserved(subpath: str) -> bool:
    """Indica se o subpath pertence a area reservada — match por SEGMENTO completo."""
    normalized = subpath.lstrip("/")
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in _RESERVED_SUBPATH_PREFIXES
    )


def _require_csp_nonce() -> str:
    """Devolve ``g.csp_nonce`` (fonte unica, hook assign_csp_nonce em app.py).

    Raises:
        500 quando o nonce nao foi atribuido — gerar um segundo nonce aqui
        divergiria do header CSP e mataria o bootstrap/anti-flash.
    """
    nonce = getattr(g, "csp_nonce", "") or ""
    if not nonce:
        current_app.logger.error(
            "g.csp_nonce ausente ao servir a shell da SPA; hook assign_csp_nonce nao rodou."
        )
        abort(500)
    return nonce


def _chatbot_base_url() -> str:
    """URL do chatbot quando habilitado; vazia = widget desligado."""
    if not current_app.config.get("CHATBOT_ENABLED"):
        return ""
    return str(current_app.config.get("CHATBOT_BASE_URL", "")).strip().rstrip("/")


def _render_spa() -> str:
    """Serve o index buildado substituindo os placeholders do shell em runtime.

    Returns:
        HTML final do shell (nonce CSP, token CSRF e config do chatbot vivos).

    Raises:
        503 com instrucao explicita quando o bundle nao foi buildado.
    """
    if not os.path.exists(_BUNDLE_INDEX_PATH):
        current_app.logger.error(_MISSING_BUNDLE_HINT)
        abort(503, description=_MISSING_BUNDLE_HINT)
    with open(_BUNDLE_INDEX_PATH, encoding="utf-8") as bundle_file:
        html = bundle_file.read()
    html = html.replace("%CSP_NONCE%", _require_csp_nonce())
    html = html.replace("%CSRF_TOKEN%", generate_csrf())
    return html.replace("%CHATBOT_BASE_URL%", str(escape(_chatbot_base_url())))


@main_bp.route("/_app/<path:asset_path>", methods=["GET"])
def spa_app_asset(asset_path: str):
    """Serve os assets imutaveis do SvelteKit (base='' -> /_app/...).

    O bundle grava os assets em ``static/spa/_app/``; com ``paths.base=''`` o
    bootstrap os referencia em ``/_app/...`` (raiz). Esta rota faz a ponte. Os
    arquivos sao versionados por hash (immutable), entao sao seguros para
    cache longo.

    Args:
        asset_path: Caminho do asset relativo a ``static/spa/_app/``.

    Returns:
        O arquivo do bundle (404 se inexistente).
    """
    return send_from_directory(_BUNDLE_APP_DIR, asset_path)


@main_bp.route("/<path:spa_path>", methods=["GET"])
def spa_native_path(spa_path: str) -> str:
    """Catch-all dinamico: serve a SPA nos paths migrados do manifesto do build.

    Tem rank menor que as rotas estaticas (Werkzeug prioriza rotas estaticas),
    entao so casa o que nenhuma rota Flask existente atendeu. Paths fora do
    manifesto (ou reservados) -> 404, preservando o comportamento atual.

    Args:
        spa_path: Caminho apos a raiz (sem barra inicial).

    Returns:
        O HTML do shell da SPA com os placeholders substituidos.
    """
    if _is_reserved(spa_path) or not _is_migrated_spa_path(spa_path):
        abort(404)
    return _render_spa()
