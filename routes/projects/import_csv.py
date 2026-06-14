"""Parsing e persistência de importação em lote de projetos via CSV.

O CSV precisa de cabeçalho com as colunas ``titulo`` e ``descricao``. A rota
Jinja ``/projects/import`` foi cortada na migração — estas funções puras são
reusadas pelo endpoint da SPA ``POST /api/projetos/importar-csv``
(``routes/api/projects_import.py``).
"""

import csv
import io
from typing import NamedTuple

from models import Project, db

from routes.shared import log_project_action

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


def _persist_imported_projects(
    rows: list[ParsedImportRow],
    orgao: "OrgaoUnidade",
    status: str,
    special_project: str | None,
    delivery_type: str | None,
):
    """Cria um Project por linha (sem etapas) com os atributos comuns escolhidos."""
    for row in rows:
        project = Project(
            titulo=row.titulo,
            short_description=row.descricao or None,
            orgao_id=orgao.id,
            orgao=orgao.sigla,
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
