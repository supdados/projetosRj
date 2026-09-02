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
from datetime import date
from typing import Literal, NamedTuple, TypedDict

from catalogs.delivery_types import normalize_delivery_type
from catalogs.inventario import sanitize_special_project_for_orgao
from models import Etapa, OrgaoUnidade, Project, db
from services.import_values import resolve_import_date, resolve_import_priority
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
DEFAULT_ETAPA_DESCRICAO = "Etapas a definir"
PROJECT_ORGAO_MAX_LEN = 100
PROJECT_TITULO_MAX_LEN = 200

TabularFileFormat = Literal["csv"]

_SEI_SPLIT_RE = re.compile(r"[;,]")


@dataclass
class ParsedImportRow:
    titulo: str
    descricao: str = ""
    status: str | None = None
    delivery_type: str | None = None
    special_project: str | None = None
    prioridade: str | None = None
    orgao: str | None = None
    area: str | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    observacao: str | None = None
    sei_numeros: list[str] = field(default_factory=list)
    ref_projeto: str | None = None
    etapa: str | None = None
    etapa_data_inicio: str | None = None
    etapa_data_fim: str | None = None
    etapa_responsavel: str | None = None
    etapa_situacao: str | None = None
    etapa_comentarios: str | None = None
    # Nº da linha na planilha (1 = cabeçalho); 0 quando desconhecido (legado).
    linha: int = 0


class AdjustedRowDetail(TypedDict):
    """Linha ajustada no import: nº na planilha, título e o que caiu no padrão."""

    linha: int
    titulo: str
    motivos: list[str]


class ImportOutcome(NamedTuple):
    imported: int
    ignored: int
    adjusted: int
    etapas_criadas: int
    ajustes: tuple[AdjustedRowDetail, ...] = ()


class _RowAttributes(NamedTuple):
    status: str
    special_project: str | None
    delivery_type: str | None
    prioridade: str | None
    data_inicio: date | None
    data_fim: date | None
    adjusted: bool
    motivos: tuple[str, ...] = ()


class _BatchContext(NamedTuple):
    """Padrões do lote resolvidos uma vez, reusados por todas as linhas."""

    area_padrao: OrgaoUnidade
    areas_por_sigla: dict[str, OrgaoUnidade]
    status: str
    special_project: str | None
    delivery_type: str | None
    prioridade: str | None = None


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
    """Lê bytes tabulares e devolve (cabeçalhos, linhas de dados)."""
    cabecalhos, numeradas = read_tabular_bytes_numbered(raw, formato)
    return cabecalhos, [linha for _, linha in numeradas]


def read_tabular_bytes_numbered(
    raw: bytes, formato: TabularFileFormat = "csv"
) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Como ``read_tabular_bytes``, com o nº da linha da planilha em cada registro.

    Único ponto do módulo que conhece o formato do arquivo.
    """
    if formato == "csv":
        return _read_csv_table(raw)
    raise ValueError(f"Formato de arquivo não suportado: {formato!r} (esperado 'csv').")


def _read_csv_rows(text: str, delimiter: str) -> list[tuple[int, list[str]]]:
    """Roda o csv.reader traduzindo ``csv.Error`` em ``ValueError`` de validação.

    Cada item carrega o nº do registro na planilha (1 = primeira linha), que
    sobrevive ao descarte de linhas fisicamente vazias — mensagens de erro do
    import apontam a linha que o usuário vê no Excel.
    """
    try:
        reader = enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1)
        return [(numero, row) for numero, row in reader if row]
    except csv.Error as csv_error:
        raise ValueError(
            f"CSV malformado ({csv_error}); cada campo deve ter no máximo "
            f"{csv.field_size_limit()} caracteres."
        )


def _is_blank_row(linha: list[str]) -> bool:
    return not any((cell or "").strip() for cell in linha)


def _drop_leading_blank_rows(
    linhas: list[tuple[int, list[str]]],
) -> list[tuple[int, list[str]]]:
    """Descarta linhas em branco só do topo; as do meio contam como ignoradas.

    O Excel escreve ``,,`` (células vazias) quando a primeira linha da planilha
    está vazia — por isso "em branco" olha as células, não o texto da linha.
    """
    for posicao, (_, linha) in enumerate(linhas):
        if not _is_blank_row(linha):
            return linhas[posicao:]
    return []


def _read_csv_table(raw: bytes) -> tuple[list[str], list[tuple[int, list[str]]]]:
    text = _decode_csv_bytes(raw)
    if not text.strip():
        raise ValueError("CSV vazio (0 linhas de conteúdo).")
    delimiter = _detect_delimiter(text)
    linhas = _drop_leading_blank_rows(_read_csv_rows(text, delimiter))
    cabecalhos = [(header or "").strip() for header in linhas[0][1]] if linhas else []
    return cabecalhos, linhas[1:]


def _cell(linha: list[str], indice: int) -> str:
    if indice < 0 or indice >= len(linha):
        return ""
    return (linha[indice] or "").strip()


def _extract_legacy_rows(
    cabecalhos: list[str], linhas: list[tuple[int, list[str]]]
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
    for numero, linha in linhas:
        titulo = _cell(linha, indices["titulo"])
        if not titulo:
            continue
        rows.append(
            ParsedImportRow(
                titulo=titulo,
                descricao=_cell(linha, indices["descricao"]),
                linha=numero,
            )
        )
    return rows


def _split_sei_values(raw: str) -> list[str]:
    return [item.strip() for item in _SEI_SPLIT_RE.split(raw) if item.strip()]


def _extract_mapped_row(
    linha: list[str], mapeamento: dict[int, str], numero: int = 0
) -> ParsedImportRow:
    valores = {campo: _cell(linha, indice) for indice, campo in mapeamento.items()}
    titulo = valores.pop("titulo", "")
    descricao = valores.pop("descricao", "")
    sei_numeros = _split_sei_values(valores.pop("sei", ""))
    opcionais = {campo: valor or None for campo, valor in valores.items()}
    return ParsedImportRow(
        titulo=titulo,
        descricao=descricao,
        sei_numeros=sei_numeros,
        linha=numero,
        **opcionais,
    )


def parse_import_rows(
    raw: bytes, mapeamento: dict[int, str] | None = None
) -> list[ParsedImportRow]:
    """Lê o arquivo tabular de projetos em ``ParsedImportRow`` por linha de dados.

    Sem ``mapeamento`` exige cabeçalho 'titulo'/'descricao' e descarta linhas sem
    título; com ``mapeamento`` (índice → campo) lê por posição e preserva linhas
    sem título para a contagem de ignoradas na persistência.
    """
    cabecalhos, linhas = read_tabular_bytes_numbered(raw)
    if mapeamento is None:
        return _extract_legacy_rows(cabecalhos, linhas)
    return [_extract_mapped_row(linha, mapeamento, numero) for numero, linha in linhas]


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


def _resolve_row_prioridade(
    value: str | None, default: str | None
) -> tuple[str | None, bool]:
    """Prioridade da linha; vazia ou irreconhecível cai no padrão do lote."""
    if not (value or "").strip():
        return default, True
    prioridade, ok = resolve_import_priority(value)
    return (prioridade if ok else default), ok


def _motivos_de_ajuste(checagens: tuple[tuple[bool, str], ...]) -> tuple[str, ...]:
    return tuple(texto for ok, texto in checagens if not ok)


def _resolve_row_attributes(
    row: ParsedImportRow,
    orgao_sigla: str | None,
    default_status: str,
    default_special: str | None,
    default_delivery: str | None,
    default_prioridade: str | None = None,
) -> _RowAttributes:
    """Aplica precedência linha > padrão do form, marcando ajuste quando o valor cai.

    Datas não têm padrão de lote: texto ilegível vira ``None`` e conta como
    ajuste.
    """
    status, status_ok = _resolve_row_status(row.status, default_status)
    special, special_ok = _resolve_row_special(
        row.special_project, orgao_sigla, default_special
    )
    delivery, delivery_ok = _resolve_row_delivery(row.delivery_type, default_delivery)
    prioridade, prioridade_ok = _resolve_row_prioridade(
        row.prioridade, default_prioridade
    )
    inicio, inicio_ok = resolve_import_date(row.data_inicio)
    fim, fim_ok = resolve_import_date(row.data_fim)
    motivos = _motivos_de_ajuste(
        (
            (status_ok, f'status "{row.status}" não reconhecido'),
            (special_ok, f'projeto especial "{row.special_project}" não reconhecido'),
            (delivery_ok, f'tipo de entrega "{row.delivery_type}" não reconhecido'),
            (prioridade_ok, f'prioridade "{row.prioridade}" não reconhecida'),
            (inicio_ok, f'data de início "{row.data_inicio}" ilegível'),
            (fim_ok, f'data de fim "{row.data_fim}" ilegível'),
        )
    )
    return _RowAttributes(
        status, special, delivery, prioridade, inicio, fim, bool(motivos), motivos
    )


def _active_areas_by_sigla() -> dict[str, OrgaoUnidade]:
    """Índice sigla→unidade ativa, montado uma vez por lote (não por linha)."""
    indice: dict[str, OrgaoUnidade] = {}
    for unidade in OrgaoUnidade.query.filter_by(ativo=True).order_by(OrgaoUnidade.id):
        indice.setdefault((unidade.sigla or "").casefold(), unidade)
    return indice


def _resolve_row_area(
    raw: str | None, areas_por_sigla: dict[str, OrgaoUnidade], default: OrgaoUnidade
) -> tuple[OrgaoUnidade, bool]:
    """Área da linha pela sigla; vazia ou desconhecida cai na área do lote."""
    sigla = (raw or "").strip()
    if not sigla:
        return default, True
    area = areas_por_sigla.get(sigla.casefold())
    if area is None:
        return default, False
    return area, True


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
    row: ParsedImportRow, area: OrgaoUnidade, attrs: _RowAttributes
) -> Project:
    """Monta o Project da linha; ``orgao`` é texto livre, independente da área."""
    return Project(
        titulo=row.titulo[:PROJECT_TITULO_MAX_LEN],
        short_description=row.descricao or None,
        orgao_id=area.id,
        orgao=(row.orgao or "").strip()[:PROJECT_ORGAO_MAX_LEN] or None,
        status=attrs.status,
        special_project=attrs.special_project,
        delivery_type=attrs.delivery_type,
        prioridade=attrs.prioridade,
        observacao=row.observacao or None,
    )


def _create_default_etapa(project: Project, attrs: _RowAttributes) -> Etapa:
    """Cria a etapa placeholder que todo projeto do modo simples recebe."""
    etapa = Etapa(
        project_id=project.id,
        descricao=DEFAULT_ETAPA_DESCRICAO,
        ordem=0,
        iniciada=False,
        done=False,
        data_inicio=attrs.data_inicio,
        data_fim=attrs.data_fim,
    )
    db.session.add(etapa)
    return etapa


def _motivos_fora_dos_attrs(
    row: ParsedImportRow, area_ok: bool, sei_dropped: int
) -> list[str]:
    """Ajustes de título, área e SEI, que ficam fora de ``_resolve_row_attributes``."""
    motivos: list[str] = []
    if len(row.titulo) > PROJECT_TITULO_MAX_LEN:
        motivos.append(f"título cortado em {PROJECT_TITULO_MAX_LEN} caracteres")
    if not area_ok:
        motivos.append(f'área responsável "{row.area}" não reconhecida')
    if sei_dropped > 0:
        motivos.append(f"{sei_dropped} processo(s) SEI inválido(s) descartado(s)")
    return motivos


def _persist_import_row(row: ParsedImportRow, contexto: _BatchContext) -> list[str]:
    """Persiste uma linha (projeto + etapa default); devolve os motivos de ajuste."""
    area, area_ok = _resolve_row_area(
        row.area, contexto.areas_por_sigla, contexto.area_padrao
    )
    attrs = _resolve_row_attributes(
        row,
        area.sigla,
        contexto.status,
        contexto.special_project,
        contexto.delivery_type,
        contexto.prioridade,
    )
    sei_kept, sei_dropped = _filter_sei_numbers(row.sei_numeros)
    project = _build_imported_project(row, area, attrs)
    db.session.add(project)
    db.session.flush()
    _create_default_etapa(project, attrs)
    if sei_kept:
        replace_project_sei_numbers(project, sei_kept)
    log_project_action(
        project_id=project.id,
        action_type="create",
        description=f'Importou o projeto "{row.titulo}" via CSV',
    )
    return list(attrs.motivos) + _motivos_fora_dos_attrs(row, area_ok, sei_dropped)


def _persist_imported_projects(
    rows: list[ParsedImportRow],
    orgao: OrgaoUnidade,
    default_status: str,
    default_special: str | None,
    default_delivery: str | None,
    default_prioridade: str | None = None,
) -> ImportOutcome:
    """Cria um Project (com a etapa default) por linha com título e conta o lote."""
    contexto = _BatchContext(
        orgao,
        _active_areas_by_sigla(),
        default_status,
        default_special,
        default_delivery,
        default_prioridade,
    )
    imported = ignored = 0
    ajustes: list[AdjustedRowDetail] = []
    for row in rows:
        if not row.titulo:
            ignored += 1
            continue
        imported += 1
        motivos = _persist_import_row(row, contexto)
        if motivos:
            ajustes.append(
                {"linha": row.linha, "titulo": row.titulo, "motivos": motivos}
            )
    db.session.commit()
    return ImportOutcome(imported, ignored, len(ajustes), imported, tuple(ajustes))
