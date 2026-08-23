"""Catálogo fixo de tipos de entrega de projeto."""

from text_folding import fold_text

DELIVERY_TYPES_OPTIONS: tuple[str, ...] = (
    "Sistema",
    "Painel",
    "Norma",
    "Instrumento de parceria",
    "Fluxo Processual",
    "Eventos",
    "Outro",
)


_DELIVERY_TYPES_BY_FOLD: dict[str, str] = {
    fold_text(option): option for option in DELIVERY_TYPES_OPTIONS
}


def normalize_delivery_type(value: str | None) -> str | None:
    """Casa value contra DELIVERY_TYPES_OPTIONS ignorando acento/caixa."""
    if value is None:
        return None
    return _DELIVERY_TYPES_BY_FOLD.get(fold_text(value))
