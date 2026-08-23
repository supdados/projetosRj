"""Neutraliza fórmulas em texto exportado/importado como CSV (CSV injection)."""

CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_csv_text(value: object) -> str:
    """Converte value para texto e prefixa aspa simples se começar com fórmula."""
    text = "" if value is None else str(value)
    if text.lstrip().startswith(CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text
