"""Normalização dos valores de célula do CSV de importação de projetos.

Puro (sem Flask/DB): cada função devolve o valor aproveitável e um sinalizador
``ok``. ``ok=False`` significa que a célula tinha conteúdo mas não foi
reconhecida — a linha conta como ajustada no relatório da importação.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import NamedTuple, TypedDict

from catalogs.priorities import normalize_priority
from text_folding import fold_text

_DATE_FORMATS: tuple[str, ...] = ("%d/%m/%Y", "%Y-%m-%d")

_SITUACOES_ETAPA_CONCLUIDA: frozenset[str] = frozenset(
    {"concluida", "concluido", "sim", "s", "x", "1", "done", "true"}
)
_SITUACOES_ETAPA_EM_ANDAMENTO: frozenset[str] = frozenset(
    {"em andamento", "andamento", "iniciada"}
)
# "Não iniciada" é o texto que o próprio export escreve — round-trip sem ajuste.
_SITUACOES_ETAPA_NAO_INICIADA: frozenset[str] = frozenset(
    {"nao iniciada", "nao iniciado"}
)


def parse_flexible_date(value: str | None) -> date | None:
    """Converte o texto de data da planilha em ``date``; irreconhecível vira ``None``.

    Aceita ``dd/mm/aaaa`` (Excel-BR) e ``aaaa-mm-dd`` (ISO). Nunca lança — o
    import precisa seguir importando a linha mesmo com a data ilegível.

    Exemplo: ``parse_flexible_date("31/12/2026") == date(2026, 12, 31)``.
    """
    texto = (value or "").strip()
    if not texto:
        return None
    for formato in _DATE_FORMATS:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def resolve_import_date(value: str | None) -> tuple[date | None, bool]:
    """Data da linha como ``(valor, ok)``; célula vazia é ``(None, True)``.

    Exemplo: ``resolve_import_date("ontem") == (None, False)``.
    """
    if not (value or "").strip():
        return None, True
    parsed = parse_flexible_date(value)
    return parsed, parsed is not None


def resolve_import_priority(value: str | None) -> tuple[str | None, bool]:
    """Prioridade da linha como ``(valor, ok)``, casada ignorando acento e caixa.

    Texto não reconhecido devolve ``(None, False)`` — quem decide o fallback
    (padrão do lote) é o chamador.

    Exemplo: ``resolve_import_priority("MÉDIA") == ("media", True)``.
    """
    texto = (value or "").strip()
    if not texto:
        return None, True
    normalizada = normalize_priority(texto)
    return normalizada, normalizada is not None


class EtapaSituacao(NamedTuple):
    iniciada: bool
    done: bool


def parse_situacao(value: str | None) -> tuple[EtapaSituacao, bool]:
    """Situação da etapa da planilha como ``(EtapaSituacao, ok)``, casada por fold.

    Concluída implica iniciada; célula vazia é "não iniciada" sem ajuste; texto
    não reconhecido também vira "não iniciada", mas com ``ok=False``.

    Exemplo: ``parse_situacao("Concluída") == (EtapaSituacao(True, True), True)``.
    """
    texto = fold_text(value or "")
    if not texto:
        return EtapaSituacao(iniciada=False, done=False), True
    if texto in _SITUACOES_ETAPA_CONCLUIDA:
        return EtapaSituacao(iniciada=True, done=True), True
    if texto in _SITUACOES_ETAPA_EM_ANDAMENTO:
        return EtapaSituacao(iniciada=True, done=False), True
    return (
        EtapaSituacao(iniciada=False, done=False),
        texto in _SITUACOES_ETAPA_NAO_INICIADA,
    )


class ResponsavelEntry(TypedDict):
    area_id: int | None
    label: str


def resolve_responsaveis_entries(
    raw: str | None, area_ids_por_sigla: dict[str, int], outras_label: str
) -> tuple[list[ResponsavelEntry], bool]:
    """Siglas de responsável (separadas por vírgula) como ``(entries, ok)``.

    Sigla casada (casefold) vira ``{area_id, label: sigla}``; desconhecida cai em
    ``{area_id: None, label: outras_label}`` e marca ``ok=False``. Dedupe por
    área; célula vazia devolve ``([], True)``.

    Exemplo: ``resolve_responsaveis_entries("vpd, XPTO", {"vpd": 7}, "Outras áreas")
    == ([{"area_id": 7, "label": "vpd"}, {"area_id": None, "label": "Outras áreas"}],
    False)``.
    """
    entries: list[ResponsavelEntry] = []
    vistos: set[int | None] = set()
    ok = True
    for sigla in (parte.strip() for parte in (raw or "").split(",")):
        if not sigla:
            continue
        area_id = area_ids_por_sigla.get(sigla.casefold())
        ok = ok and area_id is not None
        if area_id in vistos:
            continue
        vistos.add(area_id)
        label = sigla if area_id is not None else outras_label
        entries.append({"area_id": area_id, "label": label})
    return entries, ok
