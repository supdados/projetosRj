"""Órgãos autorizados a usar o projeto especial "Inventário".

A lista é fixa por regra de negócio e comparada contra a *sigla* do órgão
responsável pelo projeto. Os órgãos podem não existir no cadastro do sistema e
**não devem ser criados automaticamente** — esta constante apenas restringe onde
"Inventário" aparece como opção de projeto especial.
"""

INVENTARIO_SPECIAL_LABEL = "Inventário"

# Siglas conforme regra de negócio (comparadas case-insensitive). Podem não
# existir no cadastro de órgãos; não seedar.
INVENTARIO_ORGAO_SIGLAS: tuple[str, ...] = (
    "DIRGN",
    "DIRPE",
    "EGPE",
    "GERDG",
    "PRODER",
    "VPD",
    "VPE",
    "VPT",
)

_INVENTARIO_SIGLAS_CASEFOLD = frozenset(
    sigla.casefold() for sigla in INVENTARIO_ORGAO_SIGLAS
)


def orgao_allows_inventario(orgao_sigla: str | None) -> bool:
    """True se o órgão pode marcar projetos como "Inventário" (case-insensitive).

    Exemplo: ``orgao_allows_inventario("vpd")`` -> ``True``; ``"Auditoria"`` -> ``False``.
    """
    if not orgao_sigla:
        return False
    return orgao_sigla.strip().casefold() in _INVENTARIO_SIGLAS_CASEFOLD


def any_orgao_allows_inventario(orgao_siglas: "list[str] | None") -> bool:
    """True se ao menos uma das siglas informadas é elegível a "Inventário"."""
    if not orgao_siglas:
        return False
    return any(orgao_allows_inventario(sigla) for sigla in orgao_siglas)


def sanitize_special_project_for_orgao(
    special_project: str | None, orgao_sigla: str | None
) -> str | None:
    """Anula "Inventário" quando o órgão não é elegível; demais valores passam intactos.

    Guarda de integridade no servidor para o caso de o valor chegar via POST forjado
    ou formulário desatualizado, mesmo com a opção escondida no front.
    """
    if special_project == INVENTARIO_SPECIAL_LABEL and not orgao_allows_inventario(
        orgao_sigla
    ):
        return None
    return special_project
