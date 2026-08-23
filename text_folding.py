"""Dobra textual compartilhada para comparações insensíveis a acento e caixa."""

import unicodedata


def fold_text(value: str) -> str:
    """Normaliza value para comparação: sem acento, caixa baixa, whitespace colapsado.

    Colapsar espaços internos casa com o que o Excel entrega em célula de planilha
    (espaço duplo, quebra de linha). Exemplo: ``fold_text(" Painél  RJ ") == "painel rj"``.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.split()).casefold()
