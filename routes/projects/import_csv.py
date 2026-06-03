"""Importação em lote de projetos via upload de CSV (restrito a admin).

O CSV precisa de cabeçalho com as colunas ``titulo`` e ``descricao``. Os demais
atributos (área, projeto especial, tipo de entrega e status) são escolhidos pelo
admin no formulário e aplicados igualmente a todas as linhas importadas.
"""

import csv
import io
from typing import NamedTuple

from flask import current_app, flash, redirect, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from models import Project, db

from routes.blueprint import main_bp
from routes.decorators import admin_required, login_required
from routes.shared import (
    is_area_in_catalog,
    log_project_action,
    resolve_catalog_area_name,
)

ALLOWED_IMPORT_STATUSES = ("Vigente", "Suspenso", "Finalizado")
REQUIRED_CSV_COLUMNS = ("titulo", "descricao")


class ParsedImportRow(NamedTuple):
    titulo: str
    descricao: str


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


def _detect_delimiter(header_line: str) -> str:
    """Detecta ';' ou ',' como separador; ';' tem precedência (padrão Excel-BR)."""
    try:
        return csv.Sniffer().sniff(header_line, delimiters=";,").delimiter
    except csv.Error:
        return ";" if header_line.count(";") >= header_line.count(",") else ","


def _extract_rows(reader: "csv.DictReader") -> list[ParsedImportRow]:
    """Converte linhas do DictReader em ParsedImportRow, ignorando título vazio."""
    rows: list[ParsedImportRow] = []
    for raw_row in reader:
        # csv.DictReader joga colunas excedentes (linha com mais separadores que o
        # cabeçalho) sob a chave None como list; filtramos para não chamar .strip()
        # em list e evitar AttributeError → 500 numa importação malformada.
        normalized = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }
        titulo = normalized.get("titulo", "")
        if not titulo:
            continue
        rows.append(
            ParsedImportRow(titulo=titulo, descricao=normalized.get("descricao", ""))
        )
    return rows


def parse_import_rows(raw: bytes) -> list[ParsedImportRow]:
    """Lê CSV de projetos exigindo cabeçalho com 'titulo' e 'descricao'.

    Detecta encoding e separador automaticamente.
    Exemplo: ``parse_import_rows(b'titulo;descricao\\nA;desc')`` -> ``[('A', 'desc')]``
    """
    text = _decode_csv_bytes(raw)
    if not text.strip():
        raise ValueError("CSV vazio (0 linhas de conteúdo).")

    delimiter = _detect_delimiter(text.splitlines()[0])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [column for column in REQUIRED_CSV_COLUMNS if column not in headers]
    if missing:
        raise ValueError(
            f"Cabeçalho do CSV deve conter as colunas {REQUIRED_CSV_COLUMNS}; "
            f"faltando {missing} (encontrado {headers})."
        )
    return _extract_rows(reader)


def _resolve_import_area(area_raw: str | None) -> str | None:
    """Valida a área de destino; sinaliza erro via flash e retorna None se inválida."""
    if not area_raw:
        flash("Selecione a área de destino dos projetos.", "danger")
        return None
    if not is_area_in_catalog(area_raw):
        flash("A área selecionada é inválida ou não está mais disponível.", "danger")
        return None
    return resolve_catalog_area_name(area_raw)


def _persist_imported_projects(
    rows: list[ParsedImportRow],
    area: str,
    status: str,
    special_project: str | None,
    delivery_type: str | None,
):
    """Cria um Project por linha (sem etapas) com os atributos comuns escolhidos."""
    for row in rows:
        project = Project(
            titulo=row.titulo,
            short_description=row.descricao or None,
            area_responsavel=area,
            status=status,
            special_project=special_project,
            delivery_type=delivery_type,
        )
        db.session.add(project)
        db.session.flush()
        log_project_action(
            project_id=project.id,
            action_type="create",
            description=f'Importou o projeto "{row.titulo}" via CSV',
        )
    db.session.commit()


@main_bp.route("/projects/import", methods=["POST"])
@login_required
@admin_required
def import_projects():
    """Importa projetos de um CSV (titulo/descricao). Apenas admin."""
    area = _resolve_import_area(request.form.get("import_area"))
    if area is None:
        return redirect(url_for("main.list_projects"))

    status = request.form.get("import_status") or "Vigente"
    if status not in ALLOWED_IMPORT_STATUSES:
        flash(
            f"Status inválido: {status!r}. Use um de {ALLOWED_IMPORT_STATUSES}.",
            "danger",
        )
        return redirect(url_for("main.list_projects"))

    special_project = request.form.get("import_special_project") or None
    delivery_type = request.form.get("import_delivery_type") or None

    upload = request.files.get("import_file")
    if not upload or not upload.filename:
        flash("Selecione um arquivo CSV para importar.", "danger")
        return redirect(url_for("main.list_projects"))

    try:
        rows = parse_import_rows(upload.read())
    except ValueError as parse_error:
        flash(f"Falha ao ler o CSV: {parse_error}", "danger")
        return redirect(url_for("main.list_projects"))

    if not rows:
        flash(
            'Nenhum projeto válido encontrado no CSV (verifique a coluna "titulo").',
            "warning",
        )
        return redirect(url_for("main.list_projects"))

    try:
        _persist_imported_projects(rows, area, status, special_project, delivery_type)
    except SQLAlchemyError as db_error:
        db.session.rollback()
        current_app.logger.error("import_projects: falha ao salvar (%s)", db_error)
        flash("Erro ao salvar os projetos importados.", "danger")
        return redirect(url_for("main.list_projects"))

    flash(f"{len(rows)} projeto(s) importado(s) com sucesso.", "success")
    return redirect(url_for("main.list_projects"))
