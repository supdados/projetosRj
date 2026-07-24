"""Testes de `routes/pagination.py` — normalização de página fora de faixa."""

import pytest

from routes.pagination import clamp_page, total_pages_for


@pytest.mark.parametrize(
    ("total", "per_page", "esperado"),
    [
        (0, 40, 1),
        (1, 40, 1),
        (40, 40, 1),
        (41, 40, 2),
        (320, 40, 8),
        (321, 40, 9),
    ],
)
def test_total_pages_for(total: int, per_page: int, esperado: int) -> None:
    assert total_pages_for(total, per_page) == esperado


def test_total_pages_for_rejeita_per_page_invalido() -> None:
    with pytest.raises(ValueError, match="per_page deve ser > 0, recebido 0"):
        total_pages_for(10, 0)


@pytest.mark.parametrize(
    ("page", "total", "esperado"),
    [
        # Regressão do bug relatado: usuário na página 9, sobraram 8.
        (9, 320, (8, 8)),
        (999_999, 320, (8, 8)),
        (0, 320, (1, 8)),
        (-5, 320, (1, 8)),
        (None, 320, (1, 8)),
        (3, 320, (3, 8)),
        # Coleção vazia continua sendo "página 1 de 1", nunca página 0.
        (7, 0, (1, 1)),
    ],
)
def test_clamp_page(page: int | None, total: int, esperado: tuple[int, int]) -> None:
    assert clamp_page(page, total, 40) == esperado
