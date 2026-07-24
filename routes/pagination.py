"""Normalização de página para listas paginadas da API.

A página vem da querystring e pode estar fora de faixa por motivos legítimos:
deep-link antigo, aba aberta há muito tempo, ou itens excluídos depois que o
usuário paginou. Nesses casos a resposta correta é a ÚLTIMA página existente —
nunca uma lista vazia, que a UI não tem como distinguir de "o filtro não achou
nada".
"""


def total_pages_for(total: int, per_page: int) -> int:
    """Quantidade de páginas para `total` itens, mínimo 1 (lista vazia = 1 página).

    Exemplo:
        >>> total_pages_for(320, 40)
        8
        >>> total_pages_for(0, 40)
        1
    """
    if per_page <= 0:
        raise ValueError(f"per_page deve ser > 0, recebido {per_page!r}")
    if total <= 0:
        return 1
    return (total + per_page - 1) // per_page


def clamp_page(page: int | None, total: int, per_page: int) -> tuple[int, int]:
    """Devolve `(pagina_valida, total_de_paginas)` para `page` pedida.

    Página abaixo de 1 vira 1; acima do total vira a última existente.

    Exemplo:
        >>> clamp_page(9, 320, 40)   # sobraram 8 páginas
        (8, 8)
        >>> clamp_page(0, 320, 40)
        (1, 8)
    """
    pages = total_pages_for(total, per_page)
    return max(1, min(page or 1, pages)), pages
