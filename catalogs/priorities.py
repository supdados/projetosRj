"""Catálogo fixo de prioridades de projeto."""

from text_folding import fold_text

PRIORITY_OPTIONS: tuple[str, ...] = ("baixa", "media", "alta", "urgente")

PRIORITY_LABELS: dict[str, str] = {
    "baixa": "Baixa",
    "media": "Média",
    "alta": "Alta",
    "urgente": "Urgente",
}


_PRIORITIES_BY_FOLD: dict[str, str] = {
    fold_text(option): option for option in PRIORITY_OPTIONS
}


def normalize_priority(value: str | None) -> str | None:
    """Casa value contra PRIORITY_OPTIONS ignorando acento/caixa."""
    if value is None:
        return None
    return _PRIORITIES_BY_FOLD.get(fold_text(value))
