"""Registry de colunas, query e serialização tabular do export de projetos.

Alimenta ``GET /api/projetos/exportar`` (``routes/api/projects_export.py``).
``write_tabular_bytes`` é o único ponto que conhece o formato do arquivo.
"""

import csv
import datetime
import io
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import TYPE_CHECKING, Literal, NamedTuple

from flask_sqlalchemy.query import Query
from sqlalchemy.orm import joinedload, selectinload

from models import Etapa, IndicadorProjeto, Project, User
from services.csv_safety import safe_csv_text

if TYPE_CHECKING:
    from routes.projects.list_filters import ProjectsListFilters

TabularFileFormat = Literal["csv"]


class ExportColumn(NamedTuple):
    slug: str
    header: str
    render: Callable[[Project], str]


class StageExportColumn(NamedTuple):
    slug: str
    header: str
    render: Callable[[Etapa], str]


def _format_date(value: datetime.date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def _render_area(project: Project) -> str:
    """Área responsável = sigla da unidade vinculada; vazio quando não há vínculo."""
    if project.orgao_ref is None:
        return ""
    return safe_csv_text(project.orgao_ref.sigla)


def _render_orgao(project: Project) -> str:
    return safe_csv_text(project.orgao or "")


def _render_sei(project: Project) -> str:
    return safe_csv_text("; ".join(item.numero for item in project.sei_processes))


def _render_indicadores(project: Project) -> str:
    return safe_csv_text(
        "; ".join(ip.indicador.descricao for ip in project.indicadores if ip.indicador)
    )


def _render_cumprimento(project: Project) -> str:
    etapas = project.workflow_etapas
    if not etapas:
        return "0%"
    concluidas = sum(1 for etapa in etapas if etapa.iniciada and etapa.done)
    return f"{round(concluidas * 100 / len(etapas))}%"


EXPORT_COLUMNS: dict[str, ExportColumn] = {
    column.slug: column
    for column in (
        ExportColumn("id", "ID", lambda p: str(p.id)),
        ExportColumn("titulo", "Título", lambda p: safe_csv_text(p.titulo)),
        ExportColumn(
            "descricao", "Descrição", lambda p: safe_csv_text(p.short_description)
        ),
        ExportColumn("sei", "Processos SEI", _render_sei),
        ExportColumn("area", "Área responsável", _render_area),
        ExportColumn("orgao", "Órgão", _render_orgao),
        ExportColumn("status", "Status", lambda p: safe_csv_text(p.status)),
        ExportColumn("prioridade", "Prioridade", lambda p: safe_csv_text(p.prioridade)),
        ExportColumn(
            "data_inicio",
            "Data de início",
            lambda p: _format_date(p.data_inicio_projeto),
        ),
        ExportColumn(
            "data_fim", "Data de fim", lambda p: _format_date(p.data_fim_projeto)
        ),
        ExportColumn(
            "objetivo",
            "Objetivo EEGD",
            lambda p: safe_csv_text(p.objetivo.descricao if p.objetivo else ""),
        ),
        ExportColumn(
            "resultado",
            "Resultado EEGD",
            lambda p: safe_csv_text(
                p.resultado_esperado.descricao if p.resultado_esperado else ""
            ),
        ),
        ExportColumn("indicadores", "Indicadores EEGD", _render_indicadores),
        ExportColumn(
            "tipo_entrega", "Tipo de entrega", lambda p: safe_csv_text(p.delivery_type)
        ),
        ExportColumn(
            "projeto_especial",
            "Projeto especial",
            lambda p: safe_csv_text(p.special_project),
        ),
        ExportColumn("observacao", "Observação", lambda p: safe_csv_text(p.observacao)),
        ExportColumn(
            "total_etapas", "Total de etapas", lambda p: str(len(p.workflow_etapas))
        ),
        ExportColumn("cumprimento", "Cumprimento (%)", _render_cumprimento),
    )
}

DEFAULT_EXPORT_SLUGS: tuple[str, ...] = (
    "id",
    "titulo",
    "descricao",
    "sei",
    "area",
    "orgao",
    "status",
    "data_inicio",
    "data_fim",
    "objetivo",
    "resultado",
    "indicadores",
    "total_etapas",
    "cumprimento",
)


def _render_etapa_responsavel(etapa: Etapa) -> str:
    # Import tardio: services.etapa_responsaveis puxa routes.* e fecharia o ciclo.
    from services.etapa_responsaveis import responsavel_display

    return safe_csv_text(responsavel_display(etapa))


def _render_etapa_situacao(etapa: Etapa) -> str:
    if etapa.done:
        return "Concluída"
    if etapa.iniciada:
        return "Em andamento"
    return "Não iniciada"


EXPORT_STAGE_COLUMNS: dict[str, StageExportColumn] = {
    column.slug: column
    for column in (
        StageExportColumn("etapa", "Etapa", lambda e: safe_csv_text(e.descricao)),
        StageExportColumn(
            "etapa_data_inicio",
            "Etapa Data de início",
            lambda e: _format_date(e.data_inicio),
        ),
        StageExportColumn(
            "etapa_data_fim", "Etapa Data de fim", lambda e: _format_date(e.data_fim)
        ),
        StageExportColumn(
            "etapa_responsavel", "Etapa Responsável", _render_etapa_responsavel
        ),
        StageExportColumn("etapa_situacao", "Etapa Situação", _render_etapa_situacao),
        StageExportColumn(
            "etapa_comentarios",
            "Etapa Comentários",
            lambda e: safe_csv_text(e.comentarios or ""),
        ),
    )
}

DEFAULT_EXPORT_STAGE_SLUGS: tuple[str, ...] = tuple(EXPORT_STAGE_COLUMNS)

REF_PROJETO_HEADER = "Ref Projeto"


def build_export_query(filters: "ProjectsListFilters", user: User) -> Query:
    """Query do export: filtros da listagem + eager loading das relações lidas."""
    # Import tardio: quebra o ciclo services.project_export <-> routes.
    from routes.projects.list_filters import apply_projects_list_filters

    query = Project.query.options(
        selectinload(Project.etapas).selectinload(Etapa.responsaveis),
        selectinload(Project.sei_processes),
        selectinload(Project.indicadores).joinedload(IndicadorProjeto.indicador),
        joinedload(Project.orgao_ref),
        joinedload(Project.objetivo),
        joinedload(Project.resultado_esperado),
    )
    query = apply_projects_list_filters(query, filters, user)
    return query.order_by(Project.id)


def build_export_rows(
    projects: Iterable[Project], slugs: Sequence[str]
) -> Iterator[list[str]]:
    """Gera uma linha de valores por projeto, na ordem das colunas pedidas."""
    columns = [EXPORT_COLUMNS[slug] for slug in slugs]
    for project in projects:
        yield [column.render(project) for column in columns]


def build_export_headers_with_stages(
    slugs: Sequence[str], stage_slugs: Sequence[str]
) -> list[str]:
    """Cabeçalhos do modo com etapas: Ref Projeto + colunas de projeto + de etapa."""
    return [
        REF_PROJETO_HEADER,
        *(EXPORT_COLUMNS[slug].header for slug in slugs),
        *(EXPORT_STAGE_COLUMNS[slug].header for slug in stage_slugs),
    ]


def build_export_rows_with_stages(
    projects: Iterable[Project],
    slugs: Sequence[str],
    stage_slugs: Sequence[str],
) -> Iterator[list[str]]:
    """Gera uma linha por etapa de workflow; projeto sem etapa vira uma linha vazia.

    Exemplo:
        >>> list(build_export_rows_with_stages([projeto], ["titulo"], ["etapa"]))
        [['12', 'Portal Único', 'Planejamento']]
    """
    columns = [EXPORT_COLUMNS[slug] for slug in slugs]
    stage_columns = [EXPORT_STAGE_COLUMNS[slug] for slug in stage_slugs]
    for project in projects:
        base = [str(project.id), *(column.render(project) for column in columns)]
        etapas = project.workflow_etapas
        if not etapas:
            yield [*base, *([""] * len(stage_columns))]
            continue
        for etapa in etapas:
            yield [*base, *(column.render(etapa) for column in stage_columns)]


def write_tabular_bytes(
    cabecalhos: Sequence[str],
    linhas: Iterable[Sequence[str]],
    formato: TabularFileFormat = "csv",
) -> bytes:
    """Serializa (cabeçalhos, linhas) em bytes no formato pedido."""
    if formato == "csv":
        return _write_csv_table(cabecalhos, linhas)
    raise ValueError(f"Formato de arquivo não suportado: {formato!r} (esperado 'csv').")


def _write_csv_table(
    cabecalhos: Sequence[str], linhas: Iterable[Sequence[str]]
) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)
    writer.writerow(cabecalhos)
    writer.writerows(linhas)
    return output.getvalue().encode("utf-8-sig")
