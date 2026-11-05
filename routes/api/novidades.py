"""Endpoints JSON das Novidades (onboarding "Novidades" da SPA).

Pessoa logada:
- ``GET  /api/novidades``                → ativas, mais recente primeiro, com ``vista``.
- ``POST /api/novidades/<slug>/vista``   → fechou a novidade (``{"concluida": bool}``).

Admin (``api_admin_required``):
- ``GET  /api/admin/novidades``                      → todas, com alcance.
- ``PUT  /api/admin/novidades/<slug>``               → ``{"ativa": bool}``.
- ``POST /api/admin/novidades/<slug>/mostrar-de-novo`` → apaga as vistas.

Regras em ``services.novidades``; aqui só HTTP, envelope e commit.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request
from sqlalchemy.exc import IntegrityError

from models import Novidade, db
from services.novidades import (
    NovidadeAdmin,
    NovidadeDoUsuario,
    NovidadeInexistente,
    definir_ativa,
    listar_para_admin,
    marcar_vista,
    mostrar_de_novo,
    novidades_ativas_para,
    total_usuarios_ativos,
)
from time_utils import iso_utc

from ..blueprint import main_bp
from .envelope import fail, fail_internal, fail_not_found, ok
from .negotiation import api_admin_required, api_login_required

ApiResponse = Response | tuple[Response, int]


@main_bp.route("/api/novidades", methods=["GET"])
@api_login_required
def api_novidades_listar() -> ApiResponse:
    """Novidades ativas para a pessoa logada.

    Returns:
        ``ok({"novidades": [{slug, titulo, publicada_em, vista}]})``.
    """
    itens = novidades_ativas_para(g.user.id)
    return ok({"novidades": [_serializar_para_usuario(item) for item in itens]})


@main_bp.route("/api/novidades/<string:slug>/vista", methods=["POST"])
@api_login_required
def api_novidade_marcar_vista(slug: str) -> ApiResponse:
    """Registra que a pessoa fechou a novidade; idempotente.

    Body: ``{"concluida": bool}`` (ausente = ``false``).

    Returns:
        ``ok({"slug", "concluida"})``; 404 para novidade inexistente ou
        desligada.
    """
    concluida = (request.get_json(silent=True) or {}).get("concluida") is True
    try:
        vista = marcar_vista(g.user.id, slug, concluida=concluida)
        db.session.commit()
    except NovidadeInexistente:
        db.session.rollback()
        return fail_not_found()
    except IntegrityError:
        # Dois fechamentos simultâneos (duas abas): a outra requisição já gravou.
        db.session.rollback()
        return ok({"slug": slug, "concluida": concluida})
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "marcar novidade como vista")
    return ok({"slug": slug, "concluida": bool(vista.concluida)})


@main_bp.route("/api/admin/novidades", methods=["GET"])
@api_admin_required
def api_admin_novidades_listar() -> ApiResponse:
    """Todas as novidades com o alcance (quantos viram e concluíram).

    Returns:
        ``ok({"novidades": [...], "usuarios_ativos": int})``.
    """
    return ok(
        {
            "novidades": [_serializar_para_admin(item) for item in listar_para_admin()],
            "usuarios_ativos": total_usuarios_ativos(),
        }
    )


@main_bp.route("/api/admin/novidades/<string:slug>", methods=["PUT"])
@api_admin_required
def api_admin_novidade_definir_ativa(slug: str) -> ApiResponse:
    """Liga ou desliga uma novidade. Body: ``{"ativa": bool}``.

    Returns:
        ``ok({"novidade": {...}})``; 404 slug inexistente; 422 sem ``ativa``
        booleano.
    """
    ativa = (request.get_json(silent=True) or {}).get("ativa")
    if not isinstance(ativa, bool):
        return fail(
            f"Campo 'ativa' deve ser true ou false; recebido {ativa!r}.",
            status=422,
        )
    try:
        novidade = definir_ativa(slug, ativa)
        db.session.commit()
    except NovidadeInexistente:
        db.session.rollback()
        return fail_not_found()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "ligar/desligar novidade")
    return ok({"novidade": _serializar_novidade(novidade)})


@main_bp.route("/api/admin/novidades/<string:slug>/mostrar-de-novo", methods=["POST"])
@api_admin_required
def api_admin_novidade_mostrar_de_novo(slug: str) -> ApiResponse:
    """Apaga as vistas: a novidade volta a abrir sozinha para todos.

    Returns:
        ``ok({"removidas": int})``; 404 slug inexistente.
    """
    try:
        removidas = mostrar_de_novo(slug)
        db.session.commit()
    except NovidadeInexistente:
        db.session.rollback()
        return fail_not_found()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "mostrar novidade de novo")
    return ok({"removidas": removidas})


def _serializar_para_usuario(item: NovidadeDoUsuario) -> dict[str, Any]:
    return {
        "slug": item["slug"],
        "titulo": item["titulo"],
        "publicada_em": iso_utc(item["publicada_em"]),
        "vista": item["vista"],
    }


def _serializar_para_admin(item: NovidadeAdmin) -> dict[str, Any]:
    return {
        "slug": item["slug"],
        "titulo": item["titulo"],
        "ativa": item["ativa"],
        "publicada_em": iso_utc(item["publicada_em"]),
        "vistas": item["vistas"],
        "concluidas": item["concluidas"],
    }


def _serializar_novidade(novidade: Novidade) -> dict[str, Any]:
    return {
        "slug": novidade.slug,
        "titulo": novidade.titulo,
        "ativa": bool(novidade.ativa),
        "publicada_em": iso_utc(novidade.publicada_em),
    }
