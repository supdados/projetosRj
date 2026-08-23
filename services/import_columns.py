"""Reconhecimento de colunas do CSV de importação de projetos, por nome.

Puro (sem Flask/DB): a rota de análise usa ``suggest_column_mapping`` para
sugerir um campo por coluna e ``parse_mapping_form_value`` para revalidar o
mapeamento que o usuário confirma — a sugestão nunca é fonte de verdade.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from typing import NamedTuple, TypedDict

IMPORT_FIELDS: tuple[str, ...] = (
    "titulo",
    "descricao",
    "status",
    "delivery_type",
    "special_project",
    "observacao",
    "sei",
)

IMPORT_FIELD_LABELS: dict[str, str] = {
    "titulo": "Título",
    "descricao": "Descrição",
    "status": "Status",
    "delivery_type": "Tipo de entrega",
    "special_project": "Projeto especial",
    "observacao": "Observação",
    "sei": "Processos SEI",
}

IMPORT_FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "titulo": ("titulo", "titulo projeto", "nome", "nome projeto", "projeto", "title"),
    "descricao": (
        "descricao",
        "descricao curta",
        "descricao resumida",
        "resumo",
        "detalhes",
        "description",
    ),
    "status": ("status", "situacao"),
    "delivery_type": ("tipo entrega", "entrega", "delivery type"),
    "special_project": ("projeto especial", "especial", "marcador"),
    "observacao": (
        "observacao",
        "observacoes",
        "obs",
        "comentario",
        "comentarios",
        "nota",
        "notas",
    ),
    "sei": (
        "sei",
        "processo sei",
        "processo sei rj",
        "numero sei",
        "n sei",
        "processo",
    ),
}


class ImportFieldPayload(TypedDict):
    campo: str
    rotulo: str
    obrigatorio: bool


IMPORT_FIELDS_PAYLOAD: list[ImportFieldPayload] = [
    {
        "campo": campo,
        "rotulo": IMPORT_FIELD_LABELS[campo],
        "obrigatorio": campo == "titulo",
    }
    for campo in IMPORT_FIELDS
]


class ColumnSuggestion(NamedTuple):
    indice: int
    cabecalho: str
    campo: str | None
    confianca: str | None


_HEADER_STOPWORDS: frozenset[str] = frozenset({"de", "do", "da", "dos", "das"})
_FUZZY_THRESHOLD = 0.85
_FIELDS_HINT = ", ".join(IMPORT_FIELDS)


def _strip_accents(value: str) -> str:
    """Decompõe em NFKD e descarta combining marks ("Título" → "Titulo")."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_header(raw: str) -> str:
    """Normaliza um cabeçalho para comparação.

    Exemplo: ``normalize_header("Nome do Projeto") == "nome projeto"``.
    """
    plain = _strip_accents(raw).casefold()
    tokens = re.sub(r"[^a-z0-9]+", " ", plain).split()
    return " ".join(token for token in tokens if token not in _HEADER_STOPWORDS)


def _best_ratio(header_norm: str, alvos: tuple[str, ...]) -> float:
    """Maior razão de semelhança entre o cabeçalho e os alvos do campo."""
    return max(
        difflib.SequenceMatcher(None, header_norm, alvo).ratio() for alvo in alvos
    )


def score_field(header_norm: str, campo: str) -> tuple[float, str] | None:
    """Pontua o par (cabeçalho, campo); ``None`` quando não há semelhança suficiente.

    Exemplo: ``score_field("nome", "titulo") == (0.95, "sinonimo")``.
    """
    if not header_norm:
        return None
    rotulo_norm = normalize_header(IMPORT_FIELD_LABELS[campo])
    if header_norm in (campo, rotulo_norm):
        return (1.0, "exato")
    sinonimos = IMPORT_FIELD_SYNONYMS[campo]
    if header_norm in sinonimos:
        return (0.95, "sinonimo")
    ratio = _best_ratio(header_norm, (*sinonimos, campo, rotulo_norm))
    return (ratio, "aproximado") if ratio >= _FUZZY_THRESHOLD else None


def _rank_candidates(headers: list[str]) -> list[tuple[float, int, str, str]]:
    """Candidatos ``(score, índice, campo, confiança)`` do melhor para o pior."""
    candidatos: list[tuple[float, int, str, str]] = []
    for indice, cabecalho in enumerate(headers):
        header_norm = normalize_header(cabecalho)
        for campo in IMPORT_FIELDS:
            scored = score_field(header_norm, campo)
            if scored is not None:
                candidatos.append((scored[0], indice, campo, scored[1]))
    return sorted(candidatos, key=lambda candidato: (-candidato[0], candidato[1]))


def suggest_column_mapping(headers: list[str]) -> list[ColumnSuggestion]:
    """Sugere um campo por coluna, com unicidade dupla (um campo ↔ uma coluna).

    Exemplo: ``suggest_column_mapping(["Título"])[0].campo == "titulo"``.
    """
    escolhas: dict[int, tuple[str, str]] = {}
    campos_usados: set[str] = set()
    for _score, indice, campo, confianca in _rank_candidates(headers):
        if indice in escolhas or campo in campos_usados:
            continue
        escolhas[indice] = (campo, confianca)
        campos_usados.add(campo)
    return [
        ColumnSuggestion(indice, cabecalho, *escolhas.get(indice, (None, None)))
        for indice, cabecalho in enumerate(headers)
    ]


def _invalid_mapping_error(raw: str) -> ValueError:
    return ValueError(
        f"Mapeamento inválido: {raw!r} (esperado JSON de índice para campo)."
    )


def _load_mapping_json(raw: str) -> dict[str, object]:
    """Carrega o JSON do form ``mapeamento`` como objeto de chaves textuais."""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        raise _invalid_mapping_error(raw) from None
    if not isinstance(parsed, dict):
        raise _invalid_mapping_error(raw)
    return parsed


def _coerce_index(raw: str, chave: object) -> int:
    """Converte a chave do JSON no índice inteiro da coluna."""
    try:
        return int(str(chave).strip())
    except ValueError:
        raise _invalid_mapping_error(raw) from None


def _ensure_known_field(valor: object) -> str:
    """Garante que o valor mapeado está na whitelist de campos importáveis."""
    if isinstance(valor, str) and valor in IMPORT_FIELDS:
        return valor
    raise ValueError(
        f"Campo inválido no mapeamento: {valor!r}. Use um de {_FIELDS_HINT}."
    )


def parse_mapping_form_value(raw: str) -> dict[int, str]:
    """Valida o form ``mapeamento`` e devolve ``{índice da coluna: campo}``.

    Exemplo: ``parse_mapping_form_value('{"0":"titulo"}') == {0: "titulo"}``.
    """
    mapeamento: dict[int, str] = {}
    for chave, valor in _load_mapping_json(raw).items():
        campo = _ensure_known_field(valor)
        if campo in mapeamento.values():
            raise ValueError(f"Campo {campo!r} mapeado em mais de uma coluna.")
        mapeamento[_coerce_index(raw, chave)] = campo
    if "titulo" not in mapeamento.values():
        raise ValueError("Mapeie a coluna do título antes de importar.")
    return mapeamento
