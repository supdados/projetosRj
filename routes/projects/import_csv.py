"""Parsing e persistência de importação em lote de projetos via CSV.

Sem ``mapeamento``, o CSV exige cabeçalho com as colunas ``titulo`` e
``descricao`` (fluxo legado). Com ``mapeamento`` (índice de coluna → campo),
qualquer cabeçalho serve. Funções puras reusadas pelo endpoint da SPA
``POST /api/projetos/importar-csv`` (``routes/api/projects_import.py``).
"""

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from catalogs.delivery_types import normalize_delivery_type
from catalogs.inventario import sanitize_special_project_for_orgao
from models import OrgaoUnidade, Project, db
from services.sei_process import (
    SEI_MAX_PER_PROJECT,
    SeiProcessValidationError,
    normalize_sei_number,
    replace_project_sei_numbers,
)
from text_folding import fold_text

from routes.shared import log_project_action

ALLOWED_IMPORT_STATUSES = ("Vigente", "Suspenso", "Finalizado")
REQUIRED_CSV_COLUMNS = ("titulo", "descricao")
IMPORTABLE_SPECIAL_PROJECTS: tuple[str, ...] = (
    "ABEP",
    "TCE",
    "Fórum de simplificação",
    "Inventário",
)

TabularFileFormat = Literal["csv"]

_SEI_SPLIT_RE = re.compile(r"[;,]")


@dataclass
class ParsedImportRow:
    titulo: str
    descricao: str = ""
    status: str | None = None
    delivery_type: str | None = None
    special_project: str | None = None
    observacao: str | None = None
    sei_numeros: list[str] = field(default_factory=list)


class ImportOutcome(NamedTuple):
    imported: int
    ignored: int
    adjusted: int


class _RowAttributes(NamedTuple):
    status: str
    special_project: str | None
    delivery_type: str | None
    adjusted: bool


def _decode_csv_bytes(raw: bytes) -> str:
    """Decodifica bytes de CSV tolerando UTF-8 (com/sem BOM) e latin-1."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Não foi possível decodificar o CSV (tentado utf-8-sig/utf-8/latin-1; "
        f"{len(raw)} bytes recebidos)."
    )


def _first_content_line(text: str) -> str:
    """Primeira linha não-vazia — o cabeçalho pode vir depois de linhas em branco."""
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


def _detect_delimiter(text: str) -> str:
    """Detecta ';' ou ',' na primeira linha não-vazia; ';' tem precedência (Excel-BR)."""
    header_line = _first_content_line(text)
    try:
        return csv.Sniffer().sniff(header_line, delimiters=";,").delimiter
    except csv.Error:
        return ";" if header_line.count(";") >= header_line.count(",") else ","


def read_tabular_bytes(
    raw: bytes, formato: TabularFileFormat = "csv"
) -> tuple[list[str], list[list[str]]]:
    """Lê bytes tabulares e devolve (cabeçalhos, linhas de dados).

    Único ponto do módulo que conhece o formato do arquivo.
    """
    if formato == "csv":
        return _read_csv_table(raw)
    raise ValueError(f"Formato de arquivo não suportado: {formato!r} (esperado 'csv').")


def _read_csv_rows(text: str, delimiter: str) -> list[list[str]]:
    """Roda o csv.reader traduzindo ``csv.Error`` em ``ValueError`` de validação."""
    try:
        return [
            row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row
        ]
    except csv.Error as csv_error:
        raise ValueError(
            f"CSV malformado ({csv_error}); cada campo deve ter no máximo "
            f"{csv.field_size_limit()} caracteres."
        )


def _is_blank_row(linha: list[str]) -> bool:
    return not any((cell or "").strip() for cell in linha)


def _drop_leading_blank_rows(linhas: list[list[str]]) -> list[list[str]]:
    """Descarta linhas em branco só do topo; as do meio contam como ignoradas.

    O Excel escreve ``,,`` (células vazias) quando a primeira linha da planilha
    está vazia — por isso "em branco" olha as células, não o texto da linha.
    """
    for posicao, linha in enumerate(linhas):
        if not _is_blank_row(linha):
            return linhas[posicao:]
    return []


def _read_csv_table(raw: bytes) -> tuple[list[str], list[list[str]]]:
    text = _decode_csv_bytes(raw)
    if not text.strip():
        raise ValueError("CSV vazio (0 linhas de conteúdo).")
    delimiter = _detect_delimiter(text)
    linhas = _drop_leading_blank_rows(_read_csv_rows(text, delimiter))
    cabecalhos = [(header or "").strip() for header in linhas[0]] if linhas else []
    return cabecalhos, linhas[1:]


def _cell(linha: list[str], indice: int) -> str:
    if indice < 0 or indice >= len(linha):
        return ""
    return (linha[indice] or "").strip()


def _extract_legacy_rows(
    cabecalhos: list[str], linhas: list[list[str]]
) -> list[ParsedImportRow]:
    headers = [header.lower() for header in cabecalhos]
    missing = [column for column in REQUIRED_CSV_COLUMNS if column not in headers]
    if missing:
        raise ValueError(
            f"Cabeçalho do CSV deve conter as colunas {REQUIRED_CSV_COLUMNS}; "
            f"faltando {missing} (encontrado {headers})."
        )
    indices = {header: pos for pos, header in enumerate(headers)}
    rows: list[ParsedImportRow] = []
    for linha in linhas:
        titulo = _cell(linha, indices["titulo"])
        if not titulo:
            continue
        rows.append(
            ParsedImportRow(titulo=titulo, descricao=_cell(linha, indices["descricao"]))
        )
    return rows


def _split_sei_values(raw: str) -> list[str]:
    return [item.strip() for item in _SEI_SPLIT_RE.split(raw) if item.strip()]


def _extract_mapped_row(
    linha: list[str], mapeamento: dict[int, str]
) -> ParsedImportRow:
    valores = {campo: _cell(linha, indice) for indice, campo in mapeamento.items()}
    return ParsedImportRow(
        titulo=valores.get("titulo", ""),
        descricao=valores.get("descricao", ""),
        status=valores.get("status") or None,
        delivery_type=valores.get("delivery_type") or None,
        special_project=valores.get("special_project") or None,
        observacao=valores.get("observacao") or None,
        sei_numeros=_split_sei_values(valores.get("sei", "")),
    )


def parse_import_rows(
    raw: bytes, mapeamento: dict[int, str] | None = None
) -> list[ParsedImportRow]:
    """Lê o arquivo tabular de projetos em ``ParsedImportRow`` por linha de dados.

    Sem ``mapeamento`` exige cabeçalho 'titulo'/'descricao' e descarta linhas sem
    título; com ``mapeamento`` (índice → campo) lê por posição e preserva linhas
    sem título para a contagem de ignoradas na persistência.
    """
    cabecalhos, linhas = read_tabular_bytes(raw)
    if mapeamento is None:
        return _extract_legacy_rows(cabecalhos, linhas)
    return [_extract_mapped_row(linha, mapeamento) for linha in linhas]


def _match_folded(value: str, options: tuple[str, ...]) -> str | None:
    folded = fold_text(value)
    for option in options:
        if fold_text(option) == folded:
            return option
    return None


def _resolve_row_status(value: str | None, default: str) -> tuple[str, bool]:
    if value is None:
        return default, True
    normalized = _match_folded(value, ALLOWED_IMPORT_STATUSES)
    if normalized is None:
        return default, False
    return normalized, True


def _resolve_row_delivery(
    value: str | None, default: str | None
) -> tuple[str | None, bool]:
    if value is None:
        return default, True
    normalized = normalize_delivery_type(value)
    if normalized is None:
        return default, False
    return normalized, True


def _resolve_row_special(
    value: str | None, orgao_sigla: str | None, default: str | None
) -> tuple[str | None, bool]:
    if value is None:
        return default, True
    normalized = _match_folded(value, IMPORTABLE_SPECIAL_PROJECTS)
    if normalized is None:
        return default, False
    sanitized = sanitize_special_project_for_orgao(normalized, orgao_sigla)
    if sanitized is None:
        return default, False
    return sanitized, True


def _resolve_row_attributes(
    row: ParsedImportRow,
    orgao_sigla: str | None,
    default_status: str,
    default_special: str | None,
    default_delivery: str | None,
) -> _RowAttributes:
    """Aplica precedência linha > padrão do form, marcando ajuste quando o valor cai."""
    status, status_ok = _resolve_row_status(row.status, default_status)
    special, special_ok = _resolve_row_special(
        row.special_project, orgao_sigla, default_special
    )
    delivery, delivery_ok = _resolve_row_delivery(row.delivery_type, default_delivery)
    adjusted = not (status_ok and special_ok and delivery_ok)
    return _RowAttributes(status, special, delivery, adjusted)


def _filter_sei_numbers(values: list[str]) -> tuple[list[str], int]:
    """Separa números SEI aproveitáveis dos descartados por tamanho ou por quantidade."""
    kept: list[str] = []
    dropped = max(len(values) - SEI_MAX_PER_PROJECT, 0)
    for raw in values[:SEI_MAX_PER_PROJECT]:
        try:
            canonical = normalize_sei_number(raw)
        except SeiProcessValidationError:
            dropped += 1
            continue
        if canonical is not None:
            kept.append(raw)
    return kept, dropped


def _build_imported_project(
    row: ParsedImportRow, orgao: OrgaoUnidade, attrs: _RowAttributes
) -> Project:
    return Project(
        titulo=row.titulo,
        short_description=row.descricao or None,
        orgao_id=orgao.id,
        orgao=orgao.sigla,
        status=attrs.status,
        special_project=attrs.special_project,
        delivery_type=attrs.delivery_type,
        observacao=row.observacao or None,
    )


def _persist_import_row(
    row: ParsedImportRow,
    orgao: OrgaoUnidade,
    default_status: str,
    default_special: str | None,
    default_delivery: str | None,
) -> bool:
    attrs = _resolve_row_attributes(
        row, orgao.sigla, default_status, default_special, default_delivery
    )
    sei_kept, sei_dropped = _filter_sei_numbers(row.sei_numeros)
    project = _build_imported_project(row, orgao, attrs)
    db.session.add(project)
    db.session.flush()
    if sei_kept:
        replace_project_sei_numbers(project, sei_kept)
    log_project_action(
        project_id=project.id,
        action_type="create",
        description=f'Importou o projeto "{row.titulo}" via CSV',
    )
    return attrs.adjusted or sei_dropped > 0


def _persist_imported_projects(
    rows: list[ParsedImportRow],
    orgao: OrgaoUnidade,
    default_status: str,
    default_special: str | None,
    default_delivery: str | None,
) -> ImportOutcome:
    """Cria um Project por linha com título (sem etapas) e devolve as contagens."""
    imported = ignored = adjusted = 0
    for row in rows:
        if not row.titulo:
            ignored += 1
            continue
        row_adjusted = _persist_import_row(
            row, orgao, default_status, default_special, default_delivery
        )
        imported += 1
        adjusted += 1 if row_adjusted else 0
    db.session.commit()
    return ImportOutcome(imported, ignored, adjusted)
