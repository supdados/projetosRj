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

IMPORT_FIELDS_SIMPLE: tuple[str, ...] = (
    "titulo",
    "descricao",
    "status",
    "prioridade",
    "delivery_type",
    "special_project",
    "area",
    "orgao",
    "observacao",
    "sei",
    "data_inicio",
    "data_fim",
)

IMPORT_FIELDS_ETAPA: tuple[str, ...] = (
    "ref_projeto",
    "etapa",
    "etapa_data_inicio",
    "etapa_data_fim",
    "etapa_responsavel",
    "etapa_situacao",
    "etapa_comentarios",
)

# Superset validado em ``parse_mapping_form_value``.
IMPORT_FIELDS: tuple[str, ...] = IMPORT_FIELDS_SIMPLE + IMPORT_FIELDS_ETAPA

# Datas de projeto alimentam só a etapa default do modo simples; no modo com
# etapas as datas vêm por etapa (etapa_data_inicio/etapa_data_fim).
_CAMPOS_SO_DO_MODO_SIMPLES: frozenset[str] = frozenset({"data_inicio", "data_fim"})

IMPORT_FIELDS_COM_ETAPAS: tuple[str, ...] = (
    tuple(
        campo
        for campo in IMPORT_FIELDS_SIMPLE
        if campo not in _CAMPOS_SO_DO_MODO_SIMPLES
    )
    + IMPORT_FIELDS_ETAPA
)

REQUIRED_IMPORT_FIELDS: frozenset[str] = frozenset({"titulo"})
REQUIRED_IMPORT_FIELDS_COM_ETAPAS: frozenset[str] = frozenset(
    {"titulo", "ref_projeto", "etapa"}
)

IMPORT_MODES: tuple[str, ...] = ("simples", "com_etapas")

IMPORT_FIELD_LABELS: dict[str, str] = {
    "titulo": "Título",
    "descricao": "Descrição",
    "status": "Status",
    "prioridade": "Prioridade",
    "delivery_type": "Tipo de entrega",
    "special_project": "Projeto especial",
    "area": "Área responsável",
    "orgao": "Órgão",
    "observacao": "Observação",
    "sei": "Processos SEI",
    "data_inicio": "Data de início",
    "data_fim": "Data de fim",
    "ref_projeto": "Ref do projeto",
    "etapa": "Etapa",
    "etapa_data_inicio": "Etapa: data de início",
    "etapa_data_fim": "Etapa: data de fim",
    "etapa_responsavel": "Etapa: responsável",
    "etapa_situacao": "Etapa: situação",
    "etapa_comentarios": "Etapa: comentários",
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
    "prioridade": ("prioridade", "priority", "urgencia"),
    "delivery_type": ("tipo entrega", "entrega", "delivery type"),
    "special_project": ("projeto especial", "especial", "marcador"),
    "area": (
        "area",
        "area responsavel",
        "area demandante",
        "sigla",
        "sigla area",
        "unidade",
    ),
    "orgao": ("orgao", "orgao responsavel", "orgao demandante", "secretaria"),
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
        "processos sei",
        "processo sei rj",
        "numero sei",
        "n sei",
        "processo",
    ),
    "data_inicio": ("data inicio", "inicio", "data inicial", "inicio previsto"),
    "data_fim": ("data fim", "fim", "data final", "termino", "data termino", "prazo"),
    "ref_projeto": ("ref projeto", "ref", "referencia projeto", "referencia"),
    "etapa": ("etapa", "nome etapa", "descricao etapa", "fase"),
    "etapa_data_inicio": ("etapa data inicio", "etapa inicio", "inicio etapa"),
    "etapa_data_fim": ("etapa data fim", "etapa fim", "fim etapa", "etapa prazo"),
    "etapa_responsavel": (
        "etapa responsavel",
        "responsavel etapa",
        "area etapa",
        "etapa area",
    ),
    "etapa_situacao": (
        "etapa situacao",
        "situacao etapa",
        "etapa status",
        "status etapa",
    ),
    "etapa_comentarios": (
        "etapa comentarios",
        "comentarios etapa",
        "etapa observacao",
        "etapa comentario",
    ),
}


class ImportFieldPayload(TypedDict):
    campo: str
    rotulo: str
    obrigatorio: bool


def build_fields_payload(
    campos: tuple[str, ...], obrigatorios: frozenset[str]
) -> list[ImportFieldPayload]:
    """Monta a lista de campos oferecidos ao select de mapeamento da tela.

    Exemplo: ``build_fields_payload(("titulo",), frozenset({"titulo"}))``.
    """
    return [
        {
            "campo": campo,
            "rotulo": IMPORT_FIELD_LABELS[campo],
            "obrigatorio": campo in obrigatorios,
        }
        for campo in campos
    ]


IMPORT_FIELDS_PAYLOAD: list[ImportFieldPayload] = build_fields_payload(
    IMPORT_FIELDS_SIMPLE, REQUIRED_IMPORT_FIELDS
)


def import_mode_fields(modo: str) -> tuple[tuple[str, ...], frozenset[str]]:
    """Campos oferecidos e obrigatórios do modo de importação.

    Exemplo: ``import_mode_fields("simples") == (IMPORT_FIELDS_SIMPLE,
    frozenset({"titulo"}))``.
    """
    if modo == "simples":
        return IMPORT_FIELDS_SIMPLE, REQUIRED_IMPORT_FIELDS
    if modo == "com_etapas":
        return IMPORT_FIELDS_COM_ETAPAS, REQUIRED_IMPORT_FIELDS_COM_ETAPAS
    raise ValueError(f"Modo inválido: {modo!r}. Use um de {IMPORT_MODES}.")


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


def _rank_candidates(
    headers: list[str], fields: tuple[str, ...]
) -> list[tuple[float, int, str, str]]:
    """Candidatos ``(score, índice, campo, confiança)`` do melhor para o pior."""
    candidatos: list[tuple[float, int, str, str]] = []
    for indice, cabecalho in enumerate(headers):
        header_norm = normalize_header(cabecalho)
        for campo in fields:
            scored = score_field(header_norm, campo)
            if scored is not None:
                candidatos.append((scored[0], indice, campo, scored[1]))
    return sorted(candidatos, key=lambda candidato: (-candidato[0], candidato[1]))


def suggest_column_mapping(
    headers: list[str], fields: tuple[str, ...] = IMPORT_FIELDS
) -> list[ColumnSuggestion]:
    """Sugere um campo por coluna, com unicidade dupla (um campo ↔ uma coluna).

    ``fields`` restringe as sugestões aos campos do modo pedido.

    Exemplo: ``suggest_column_mapping(["Título"])[0].campo == "titulo"``.
    """
    escolhas: dict[int, tuple[str, str]] = {}
    campos_usados: set[str] = set()
    for _score, indice, campo, confianca in _rank_candidates(headers, fields):
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


def _ensure_field_in_mode(
    campo: str, campos_do_modo: tuple[str, ...], modo: str
) -> None:
    """Recusa campo válido no superset mas fora do modo pedido (ex.: etapa no simples)."""
    if campo in campos_do_modo:
        return
    raise ValueError(
        f"Campo {campo!r} não está disponível no modo {modo!r}. "
        f"Use um de {', '.join(campos_do_modo)}."
    )


_REQUIRED_FIELD_ERRORS: dict[str, str] = {
    "titulo": "Mapeie a coluna do título antes de importar.",
    "ref_projeto": (
        "Mapeie a coluna da referência do projeto (Ref do projeto) no modo com etapas."
    ),
    "etapa": "Mapeie a coluna da etapa no modo com etapas.",
}


def _ensure_required_mapped(
    campos_mapeados: set[str], obrigatorios: frozenset[str]
) -> None:
    for campo in ("titulo", "ref_projeto", "etapa"):
        if campo in obrigatorios and campo not in campos_mapeados:
            raise ValueError(_REQUIRED_FIELD_ERRORS[campo])


def parse_mapping_form_value(raw: str, modo: str = "simples") -> dict[int, str]:
    """Valida o form ``mapeamento`` e devolve ``{índice da coluna: campo}``.

    ``modo`` restringe os campos aceitos e define os obrigatórios (o modo com
    etapas exige também ``ref_projeto`` e ``etapa``).

    Exemplo: ``parse_mapping_form_value('{"0":"titulo"}') == {0: "titulo"}``.
    """
    campos_do_modo, obrigatorios = import_mode_fields(modo)
    mapeamento: dict[int, str] = {}
    for chave, valor in _load_mapping_json(raw).items():
        campo = _ensure_known_field(valor)
        _ensure_field_in_mode(campo, campos_do_modo, modo)
        if campo in mapeamento.values():
            raise ValueError(f"Campo {campo!r} mapeado em mais de uma coluna.")
        mapeamento[_coerce_index(raw, chave)] = campo
    _ensure_required_mapped(set(mapeamento.values()), obrigatorios)
    return mapeamento
