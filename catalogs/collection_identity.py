"""Identidade visual das coleções de projetos (ícone + família de cor).

Whitelist única compartilhada entre o ``@validates`` do modelo
(``models/project_collection.py``), o service (``services/project_collections.py``)
e o registry do frontend (``lib/icons/collectionIcons.ts`` espelha os ids).
``cor`` é sempre NOME de família da régua — nunca hex (o Tailwind do projeto
substitui a paleta; hex cru não compila).
"""

COLLECTION_ICONS: frozenset[str] = frozenset(
    {
        "camadas",
        "servidores",
        "pessoas",
        "documento",
        "estrela",
        "rede",
        "capacitacao",
        "calendario",
    }
)

COLLECTION_COLORS: frozenset[str] = frozenset(
    {
        "primary",
        "success",
        "warning",
        "attention",
        "danger",
        "neutral",
    }
)

DEFAULT_COLLECTION_ICON = "camadas"
DEFAULT_COLLECTION_COLOR = "primary"

FAVORITOS_ICON = "estrela"
FAVORITOS_COLOR = "warning"
