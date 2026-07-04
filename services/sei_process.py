"""Normalização e persistência dos números de processo SEI de um projeto.

O formato canônico é "SEI-380001/000664/2026", mas a entrada é tolerante:
o prefixo "SEI-" é opcional (com qualquer caixa/espaçamento) e texto legado
que não começa com dígito passa verbatim — nunca mutilar dado de produção.
"""

import re

from models import Project, ProjectSeiProcess

_SEI_PREFIX_RE = re.compile(r"^sei[\s-]*", re.IGNORECASE)
SEI_NUMBER_MAX_LENGTH = 50  # limite da coluna VARCHAR(50)
SEI_MAX_PER_PROJECT = 20  # sanidade contra payload abusivo


class SeiProcessValidationError(ValueError):
    """Processo SEI inválido (tamanho ou tipo)."""


def normalize_sei_number(raw: str) -> str | None:
    """Canoniza um número SEI: '380001/000664/2026' -> 'SEI-380001/000664/2026'.

    Aceita entrada com ou sem prefixo ('sei- 380001/...' também). Retorna
    None para entrada vazia; texto sem dígito inicial passa verbatim.
    """
    value = " ".join((raw or "").split())
    if not value:
        return None
    remainder = _SEI_PREFIX_RE.sub("", value)
    canonical = f"SEI-{remainder}" if remainder[:1].isdigit() else value
    if len(canonical) > SEI_NUMBER_MAX_LENGTH:
        raise SeiProcessValidationError(
            f"Processo SEI {raw!r} excede {SEI_NUMBER_MAX_LENGTH} caracteres "
            "(esperado: SEI-380001/000664/2026)."
        )
    return canonical


def normalize_sei_number_or_raw(raw: str) -> str:
    """Backfill de legado: canoniza; se estourar o limite, preserva cru truncado."""
    try:
        return normalize_sei_number(raw) or ""
    except SeiProcessValidationError:
        return raw.strip()[:SEI_NUMBER_MAX_LENGTH]


def normalize_sei_list(values: list[str]) -> list[str]:
    """Normaliza cada item, descarta vazios e deduplica (case-insensitive)."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        canonical = normalize_sei_number(raw)
        if canonical is None or canonical.lower() in seen:
            continue
        seen.add(canonical.lower())
        result.append(canonical)
    return result


def replace_project_sei_numbers(
    project: Project, raw_numbers: list[str]
) -> tuple[list[str], list[str]]:
    """Substitui a coleção inteira de números SEI do projeto (ordem = ordem da lista).

    Retorna (antes, depois). No-op quando iguais; lista vazia esvazia a
    coleção via delete-orphan.
    """
    new_numbers = normalize_sei_list(raw_numbers)
    old_numbers = [item.numero for item in project.sei_processes]
    if old_numbers == new_numbers:
        return old_numbers, new_numbers
    # Reusa as linhas existentes (UPDATE) em vez de recriá-las: o flush do
    # SQLAlchemy insere antes de deletar, e delete+insert do mesmo numero
    # violaria a UNIQUE(project_id, numero).
    existing_by_key = {item.numero.lower(): item for item in project.sei_processes}
    rebuilt: list[ProjectSeiProcess] = []
    for index, numero in enumerate(new_numbers):
        item = existing_by_key.pop(numero.lower(), None)
        if item is None:
            item = ProjectSeiProcess(numero=numero)
        item.numero = numero
        item.ordem = index
        rebuilt.append(item)
    project.sei_processes = rebuilt
    # Espelho na coluna legada (expand-contract, 1 release): rollback do deploy
    # continua exibindo o primeiro número em vez de "vazio".
    project.sei_process = new_numbers[0] if new_numbers else None
    return old_numbers, new_numbers
