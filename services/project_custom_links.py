"""Substituição da coleção de links customizados de um projeto.

Molde de ``services/sei_process.py::replace_project_sei_numbers``: substituição
por posição (``ordem``), lista vazia esvazia via delete-orphan. Sem UniqueConstraint,
então as linhas são reusadas por índice (não há colisão a evitar como no SEI).
"""

from __future__ import annotations

from models import Project, ProjectCustomLink
from services.link_validation import (
    CUSTOM_LINK_MAX_PER_PROJECT,
    LinkValidationError,
    normalize_link_label,
    normalize_link_url,
)


def _coerce_link_entry(entry: object) -> dict[str, str | None]:
    if not isinstance(entry, dict):
        raise LinkValidationError(
            "Cada link personalizado deve ser um objeto {label, url}; "
            f"recebido {type(entry).__name__}."
        )
    return {"label": entry.get("label") or "", "url": entry.get("url")}


def parse_custom_links_payload(raw: object) -> list[dict[str, str | None]]:
    """Valida a FORMA do payload ``custom_links`` (lista de objetos, teto de itens).

    Compartilhado pela criação (``projects_write``) e pelo PATCH inline (``ajax``);
    o conteúdo de cada par é validado por ``replace_project_custom_links``.

    Raises:
        LinkValidationError: quando não é lista de objetos ou excede o teto.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise LinkValidationError(
            "Links personalizados devem ser uma lista de objetos; "
            f"recebido {type(raw).__name__}."
        )
    if len(raw) > CUSTOM_LINK_MAX_PER_PROJECT:
        raise LinkValidationError(
            f"Máximo de {CUSTOM_LINK_MAX_PER_PROJECT} links personalizados; "
            f"recebidos {len(raw)}."
        )
    return [_coerce_link_entry(entry) for entry in raw]


def _normalize_link_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Valida e normaliza cada par ``{label, url}``, cortando em 3 itens."""
    result: list[dict[str, str]] = []
    for item in items[:CUSTOM_LINK_MAX_PER_PROJECT]:
        label = normalize_link_label(item.get("label", ""))
        url = normalize_link_url(item.get("url"))
        if url is None:
            raise LinkValidationError(
                f"Link {label!r} sem URL (esperado: http(s)://dominio)."
            )
        result.append({"label": label, "url": url})
    return result


def replace_project_custom_links(
    project: Project, items: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Substitui a coleção inteira de links customizados (ordem = ordem da lista).

    Retorna (antes, depois) como listas de ``{label, url}``. No-op quando iguais;
    lista vazia esvazia a coleção via delete-orphan.
    """
    new_links = _normalize_link_items(items)
    old_links = [{"label": row.label, "url": row.url} for row in project.custom_links]
    if old_links == new_links:
        return old_links, new_links
    existing = list(project.custom_links)
    rebuilt: list[ProjectCustomLink] = []
    for index, link in enumerate(new_links):
        row = existing[index] if index < len(existing) else ProjectCustomLink()
        row.label = link["label"]
        row.url = link["url"]
        row.ordem = index
        rebuilt.append(row)
    project.custom_links = rebuilt
    return old_links, new_links
