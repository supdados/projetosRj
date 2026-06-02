"""Envelope canônico de respostas JSON da API da SPA.

Toda rota nova de dados consumida pelo frontend SvelteKit deve responder no
formato único abaixo, para que o cliente (``client.ts``) possa desempacotar de
forma uniforme:

    sucesso:  {"ok": true,  "data": <payload>, "meta": <opcional>}
    erro:     {"ok": false, "error": {"code": <str>, "message": <str>}}

Códigos de erro canônicos (``code``):
    "unauthenticated" | "forbidden" | "not_found" | "validation" | "server"

NÃO ENVELOPAR (exceções deliberadas):
    - ``/webhook`` (``routes/calendars/webhook.py``): responde text/plain cru
      (``("", 204)`` / ``("token mismatch", 403)``); o Google espera corpo cru.
    - Downloads binários: CSV de projetos (``routes/projects/views.py``) e
      ``send_file`` de anexos — são octet-stream/CSV, não JSON.
    - Endpoints legados (``routes/api/legacy.py``) mantidos por compatibilidade.

Exemplo de uso:
    >>> return ok({"id": 1, "name": "Ana"})
    >>> return ok(items, meta={"page": 1, "page_size": 20, "total": 42})
    >>> return fail("Projeto não encontrado", status=404, code="not_found")
"""

from __future__ import annotations

from typing import Any

from flask import Response, jsonify


def ok(
    data: Any = None,
    *,
    meta: dict[str, Any] | None = None,
    **extra: Any,
) -> Response:
    """Monta uma resposta de sucesso no envelope canônico.

    Args:
        data: Payload serializável a ser entregue em ``data`` (pode ser ``None``).
        meta: Metadados opcionais (ex.: paginação ``{page, page_size, total}``);
            omitido do corpo quando ``None``.
        **extra: Campos adicionais de topo no envelope (ex.: ``count=...``).
            Use com parcimônia; o contrato padrão é ``{ok, data, meta}``.

    Returns:
        ``flask.Response`` JSON com ``{"ok": true, "data": ..., [meta]}`` e
        HTTP 200.

    Exemplo:
        >>> return ok({"token": "abc"})
    """
    body: dict[str, Any] = {"ok": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    if extra:
        body.update(extra)
    return jsonify(body)


def fail(
    message: str,
    status: int = 400,
    code: str = "validation",
) -> tuple[Response, int]:
    """Monta uma resposta de erro no envelope canônico.

    Args:
        message: Mensagem legível para o usuário/desenvolvedor.
        status: Código HTTP a retornar (default 400).
        code: Código de erro canônico
            ("unauthenticated" | "forbidden" | "not_found" | "validation" |
            "server").

    Returns:
        Tupla ``(flask.Response, status)`` com corpo
        ``{"ok": false, "error": {"code": ..., "message": ...}}``.

    Exemplo:
        >>> return fail("Sessão expirada", status=401, code="unauthenticated")
    """
    body: dict[str, Any] = {
        "ok": False,
        "error": {"code": code, "message": message},
    }
    return jsonify(body), status
