"""Monta path e kwargs de request a partir dos casos declarativos de rota."""

from io import BytesIO
from typing import Any, Mapping


class DummyIdContext(dict):
    """Contexto de format() que devolve um id ficticio para chaves ausentes.

    A negacao a anonimo/nao-admin nao depende do id concreto na URL (o guard
    rejeita ANTES de qualquer lookup), entao um placeholder e suficiente quando
    o ``seed_data`` nao expoe a chave (ex.: ``anexo_id`` vive em outra lane de
    seed). Mantem o teste de permissao auto-suficiente sem tocar o seed.
    """

    def __missing__(self, key: str) -> str:
        return "1"


def format_payload(value: Any, context: Mapping[str, Any]) -> Any:
    """Interpola recursivamente as strings do payload com o contexto do seed."""
    if isinstance(value, str):
        return value.format_map(context)
    if isinstance(value, list):
        return [format_payload(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(format_payload(item, context) for item in value)
    if isinstance(value, dict):
        return {key: format_payload(item, context) for key, item in value.items()}
    return value


def resolve_request(
    case: Mapping[str, Any],
    seed_data: Mapping[str, Any],
    *,
    fallback_ids: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Resolve o path e os kwargs de ``client.open`` de um caso de rota."""
    context = DummyIdContext(seed_data) if fallback_ids else dict(seed_data)
    path = case["path"].format_map(context)
    request_kwargs: dict[str, Any] = {}
    for key in ("data", "json", "headers", "query_string"):
        if key in case:
            request_kwargs[key] = format_payload(case[key], context)
    if "files" in case:
        request_kwargs["data"] = {
            field: (BytesIO(magic_bytes), filename)
            for field, (magic_bytes, filename) in case["files"].items()
        }
        request_kwargs["content_type"] = "multipart/form-data"
    return path, request_kwargs
