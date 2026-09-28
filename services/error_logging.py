"""Registro estruturado de falhas, compartilhado por rotas e serviços."""

import json

from flask import current_app, has_request_context, request


def log_internal_error(exc: Exception, operation: str) -> None:
    """Registra a causa e o contexto sem copiar corpo, cookies ou tokens do request."""
    details = {
        "event": "api_internal_error",
        "operation": operation,
        "error_type": type(exc).__name__,
        "path": request.path if has_request_context() else None,
        "method": request.method if has_request_context() else None,
    }
    current_app.logger.error(
        json.dumps(details, ensure_ascii=False),
        extra=details,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
