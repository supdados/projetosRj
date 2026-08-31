"""Endpoint JSON de importação de projetos via CSV (Admin) consumido pela SPA.

Sucessor da rota Jinja ``/projects/import`` (``routes/projects/import_csv.py``):
reusa a MESMA lógica pura de parsing (``parse_import_rows``) e persistência
(``_persist_imported_projects``), apenas trocando o ``flash`` + redirect do fluxo
Jinja pelo envelope canônico (``ok``/``fail``). Restrito a admin via
``api_admin_required``.

Inclui também ``POST /api/projetos/importar-csv/analise``, que apenas inspeciona
o arquivo enviado (nada é persistido) e devolve as colunas detectadas para a
tela de revisão do mapeamento.
"""

from __future__ import annotations

from typing import TypedDict

from flask import Response, request
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage

from catalogs.inventario import sanitize_special_project_for_orgao
from catalogs.priorities import PRIORITY_OPTIONS, normalize_priority
from models import OrgaoUnidade, db
from services.import_columns import (
    IMPORT_MODES,
    ImportFieldPayload,
    build_fields_payload,
    import_mode_fields,
    parse_mapping_form_value,
    suggest_column_mapping,
)

from ..blueprint import main_bp
from ..projects.import_csv import (
    ALLOWED_IMPORT_STATUSES,
    AdjustedRowDetail,
    ImportOutcome,
    ParsedImportRow,
    _cell,
    _decode_csv_bytes,
    _detect_delimiter,
    _persist_imported_projects,
    parse_import_rows,
    read_tabular_bytes,
)
from ..projects.import_stages import _persist_imported_projects_with_stages
from .envelope import fail, ok
from .negotiation import api_admin_required

MAX_IMPORT_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
MAX_IMPORT_COLUMNS = 200


class ColumnPreview(TypedDict):
    indice: int
    cabecalho: str
    campo: str | None
    confianca: str | None
    amostra: str


class ImportAnalysisPayload(TypedDict):
    delimitador: str
    total_linhas: int
    modo: str
    colunas: list[ColumnPreview]
    campos: list[ImportFieldPayload]


def _resolve_import_modo(modo_raw: str | None) -> str:
    """Modo do lote vindo do form; ausente ou vazio cai no modo simples."""
    modo = (modo_raw or "").strip() or "simples"
    if modo not in IMPORT_MODES:
        raise ValueError(f"Modo inválido: {modo!r}. Use um de {IMPORT_MODES}.")
    return modo


def _resolve_import_orgao(orgao_id_raw: str | None) -> OrgaoUnidade:
    """Resolve o órgão de destino do lote a partir do form."""
    if not orgao_id_raw:
        raise ValueError("Selecione o órgão de destino dos projetos.")
    try:
        orgao_id = int(orgao_id_raw)
    except (TypeError, ValueError):
        raise ValueError(f"Órgão inválido: {orgao_id_raw!r} (esperado id numérico).")
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None or not orgao.ativo:
        raise ValueError("O órgão selecionado é inválido ou não está mais disponível.")
    return orgao


def _resolve_import_status(status_raw: str | None) -> str:
    """Status padrão do lote, aplicado às linhas sem status próprio."""
    status = status_raw or "Vigente"
    if status not in ALLOWED_IMPORT_STATUSES:
        raise ValueError(
            f"Status inválido: {status!r}. Use um de {ALLOWED_IMPORT_STATUSES}."
        )
    return status


def _resolve_import_prioridade(prioridade_raw: str | None) -> str | None:
    """Prioridade padrão do lote; ausente ou vazia significa sem prioridade."""
    if not (prioridade_raw or "").strip():
        return None
    prioridade = normalize_priority(prioridade_raw)
    if prioridade is None:
        raise ValueError(
            f"Prioridade inválida: {prioridade_raw!r}. Use uma de {PRIORITY_OPTIONS}."
        )
    return prioridade


def _resolve_import_mapping(
    mapeamento_raw: str | None, modo: str
) -> dict[int, str] | None:
    """Mapeamento índice→campo do form; obrigatório no modo com etapas.

    No modo simples, ausente devolve ``None`` (cabeçalho legado
    ``titulo``/``descricao``).
    """
    if not mapeamento_raw or not mapeamento_raw.strip():
        if modo == "com_etapas":
            raise ValueError(
                "O modo com etapas exige o mapeamento de colunas "
                "(form 'mapeamento' ausente)."
            )
        return None
    return parse_mapping_form_value(mapeamento_raw, modo)


def _oversized_upload_message() -> str:
    return (
        f"Arquivo acima de 2 MB (limite {MAX_IMPORT_UPLOAD_BYTES} bytes por arquivo)."
    )


def _read_capped_upload(upload: FileStorage) -> bytes:
    """Lê o upload recusando arquivo acima de ``MAX_IMPORT_UPLOAD_BYTES``.

    Mede só o arquivo: ``request.content_length`` é o corpo multipart inteiro e
    recusaria arquivos abaixo do teto por causa do overhead das bordas.
    """
    raw = upload.read(MAX_IMPORT_UPLOAD_BYTES + 1)
    if len(raw) > MAX_IMPORT_UPLOAD_BYTES:
        raise ValueError(_oversized_upload_message())
    return raw


def _ensure_rows_cap(rows: list[ParsedImportRow]) -> None:
    """Recusa lotes acima de ``MAX_IMPORT_ROWS`` linhas com título, antes de persistir."""
    importaveis = sum(1 for row in rows if row.titulo)
    if importaveis > MAX_IMPORT_ROWS:
        raise ValueError("Importação acima de 10.000 projetos — divida o arquivo.")


def _parse_upload_rows(
    raw: bytes, mapeamento: dict[int, str] | None
) -> list[ParsedImportRow]:
    try:
        rows = parse_import_rows(raw, mapeamento)
    except ValueError as parse_error:
        raise ValueError(f"Falha ao ler o CSV: {parse_error}")
    if not rows:
        raise ValueError(
            'Nenhum projeto válido encontrado no CSV (verifique a coluna "titulo").'
        )
    return rows


def _read_import_rows(
    upload: FileStorage | None, mapeamento: dict[int, str] | None
) -> list[ParsedImportRow]:
    """Lê o arquivo enviado em linhas de importação."""
    if upload is None or not upload.filename:
        raise ValueError("Selecione um arquivo CSV para importar.")
    rows = _parse_upload_rows(_read_capped_upload(upload), mapeamento)
    _ensure_rows_cap(rows)
    return rows


def _batch_defaults(orgao: OrgaoUnidade) -> tuple[str | None, str | None]:
    """Projeto especial e tipo de entrega padrão do lote, vindos do form."""
    special_project = sanitize_special_project_for_orgao(
        request.form.get("special_project") or None, orgao.sigla
    )
    return special_project, request.form.get("delivery_type") or None


def _import_counts(
    outcome: ImportOutcome,
) -> dict[str, int | list[AdjustedRowDetail]]:
    return {
        "imported_count": outcome.imported,
        "ignored_count": outcome.ignored,
        "adjusted_count": outcome.adjusted,
        "etapas_criadas": outcome.etapas_criadas,
        "adjusted_rows": list(outcome.ajustes),
    }


def _persist_import_batch(
    modo: str,
    rows: list[ParsedImportRow],
    orgao: OrgaoUnidade,
    status: str,
    special_project: str | None,
    delivery_type: str | None,
    prioridade: str | None,
) -> ImportOutcome:
    """Despacha a persistência do lote para o fluxo do modo pedido."""
    if modo == "com_etapas":
        return _persist_imported_projects_with_stages(
            rows, orgao, status, special_project, delivery_type, prioridade
        )
    return _persist_imported_projects(
        rows, orgao, status, special_project, delivery_type, prioridade
    )


@main_bp.route("/api/projetos/importar-csv", methods=["POST"])
@api_admin_required
def api_projetos_importar_csv() -> Response | tuple[Response, int]:
    """Importa projetos em lote de um CSV.

    Aceita ``multipart/form-data`` com o arquivo em ``arquivo`` (até 2 MB e
    10.000 projetos), o ``modo`` opcional (``simples``/``com_etapas``), os
    atributos padrão do lote (``orgao_id`` obrigatório, ``status``,
    ``special_project``, ``delivery_type``, ``prioridade``) e o ``mapeamento``
    (JSON de índice
    de coluna para campo) — opcional no modo simples (sem ele o CSV precisa das
    colunas ``titulo``/``descricao``) e obrigatório no modo com etapas, que lê
    1 linha por etapa agrupada por ``ref_projeto``. No modo simples todo
    projeto nasce com a etapa "Etapas a definir".

    Returns:
        ``ok({"imported_count", "ignored_count", "adjusted_count",
        "etapas_criadas", "adjusted_rows"})`` em sucesso, onde ``adjusted_rows``
        detalha cada linha ajustada (``{linha, titulo, motivos}``);
        ``fail(..., 422, "validation")`` para
        entradas inválidas; ``fail(..., 500, "server")`` em erro de persistência.
    """
    try:
        modo = _resolve_import_modo(request.form.get("modo"))
        orgao = _resolve_import_orgao(request.form.get("orgao_id"))
        status = _resolve_import_status(request.form.get("status"))
        prioridade = _resolve_import_prioridade(request.form.get("prioridade"))
        mapeamento = _resolve_import_mapping(request.form.get("mapeamento"), modo)
        rows = _read_import_rows(request.files.get("arquivo"), mapeamento)
    except ValueError as invalid_input:
        return fail(str(invalid_input), status=422, code="validation")

    special_project, delivery_type = _batch_defaults(orgao)
    try:
        outcome = _persist_import_batch(
            modo, rows, orgao, status, special_project, delivery_type, prioridade
        )
    except ValueError as invalid_rows:
        db.session.rollback()
        return fail(str(invalid_rows), status=422, code="validation")
    except SQLAlchemyError:
        db.session.rollback()
        return fail("Erro ao salvar os projetos importados.", status=500, code="server")

    return ok(_import_counts(outcome))


def _first_sample(linhas: list[list[str]], indice: int) -> str:
    """Primeiro valor não-vazio da coluna ``indice`` entre as linhas de dados."""
    for linha in linhas:
        valor = _cell(linha, indice)
        if valor:
            return valor
    return ""


def _detected_delimiter(raw: bytes) -> str:
    return _detect_delimiter(_decode_csv_bytes(raw))


def _build_columns_preview(
    cabecalhos: list[str], linhas: list[list[str]], campos: tuple[str, ...]
) -> list[ColumnPreview]:
    return [
        {
            "indice": sugestao.indice,
            "cabecalho": sugestao.cabecalho,
            "campo": sugestao.campo,
            "confianca": sugestao.confianca,
            "amostra": _first_sample(linhas, sugestao.indice),
        }
        for sugestao in suggest_column_mapping(cabecalhos, campos)
    ]


def _analysable_table(raw: bytes) -> tuple[list[str], list[list[str]]]:
    """Lê a tabela para análise recusando cabeçalhos acima de ``MAX_IMPORT_COLUMNS``."""
    try:
        cabecalhos, linhas = read_tabular_bytes(raw)
    except ValueError as parse_error:
        raise ValueError(f"Falha ao ler o CSV: {parse_error}")
    if len(cabecalhos) > MAX_IMPORT_COLUMNS:
        raise ValueError(f"Arquivo acima de 200 colunas (recebidas {len(cabecalhos)}).")
    return cabecalhos, linhas


def _build_analysis_payload(
    raw: bytes, cabecalhos: list[str], linhas: list[list[str]], modo: str
) -> ImportAnalysisPayload:
    campos, obrigatorios = import_mode_fields(modo)
    return {
        "delimitador": _detected_delimiter(raw),
        "total_linhas": len(linhas),
        "modo": modo,
        "colunas": _build_columns_preview(cabecalhos, linhas, campos),
        "campos": build_fields_payload(campos, obrigatorios),
    }


@main_bp.route("/api/projetos/importar-csv/analise", methods=["POST"])
@api_admin_required
def api_projetos_importar_csv_analise() -> Response | tuple[Response, int]:
    """Analisa o CSV enviado e sugere o mapeamento de colunas, sem persistir nada.

    Recebe ``multipart/form-data`` com o arquivo em ``arquivo`` (até 2 MB) e o
    ``modo`` opcional, devolvendo
    ``ok({delimitador, total_linhas, modo, colunas, campos})`` — campos e
    sugestões restritos aos campos do modo pedido.
    """
    upload = request.files.get("arquivo")
    if not upload or not upload.filename:
        return fail(
            "Selecione um arquivo CSV para importar.", status=422, code="validation"
        )

    try:
        modo = _resolve_import_modo(request.form.get("modo"))
        raw = _read_capped_upload(upload)
        cabecalhos, linhas = _analysable_table(raw)
    except ValueError as invalid_input:
        return fail(str(invalid_input), status=422, code="validation")

    return ok(_build_analysis_payload(raw, cabecalhos, linhas, modo))
