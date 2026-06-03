"""Áreas autorizadas a usar o projeto especial "Inventário".

A lista é fixa por regra de negócio. As áreas podem não existir no catálogo do
sistema e **não devem ser criadas automaticamente** — esta constante apenas
restringe onde "Inventário" aparece como opção de projeto especial.
"""

INVENTARIO_SPECIAL_LABEL = "Inventário"

# Nomes conforme regra de negócio (comparados case-insensitive). Podem não existir
# no AreaCatalog; não seedar.
INVENTARIO_AREAS: tuple[str, ...] = (
    "DIRGN",
    "DIRPE",
    "EGPE",
    "GERDG",
    "PRODER",
    "VPD",
    "VPE",
    "VPT",
)

_INVENTARIO_AREAS_CASEFOLD = frozenset(name.casefold() for name in INVENTARIO_AREAS)


def area_allows_inventario(area_name: str | None) -> bool:
    """True se a área pode marcar projetos como "Inventário" (case-insensitive).

    Exemplo: ``area_allows_inventario("vpd")`` -> ``True``; ``"Auditoria"`` -> ``False``.
    """
    if not area_name:
        return False
    return area_name.strip().casefold() in _INVENTARIO_AREAS_CASEFOLD


def any_area_allows_inventario(area_names: "list[str] | None") -> bool:
    """True se ao menos uma das áreas informadas é elegível a "Inventário"."""
    if not area_names:
        return False
    return any(area_allows_inventario(name) for name in area_names)


def sanitize_special_project_for_area(
    special_project: str | None, area_name: str | None
) -> str | None:
    """Anula "Inventário" quando a área não é elegível; demais valores passam intactos.

    Guarda de integridade no servidor para o caso de o valor chegar via POST forjado
    ou formulário desatualizado, mesmo com a opção escondida no front.
    """
    if special_project == INVENTARIO_SPECIAL_LABEL and not area_allows_inventario(
        area_name
    ):
        return None
    return special_project
