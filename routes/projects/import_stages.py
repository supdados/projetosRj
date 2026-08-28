"""Agrupamento e persistência do modo com etapas do import de projetos via CSV.

Formato longo: 1 linha = 1 etapa; ``ref_projeto`` amarra as linhas do mesmo
projeto (grupos contíguos; campos de projeto herdados da 1ª linha, que vence
divergências). Reusa o parsing e a montagem de projeto do modo simples
(``routes/projects/import_csv``). Reimportar sempre cria projetos novos — a
ref é só amarração intra-arquivo.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from models import Etapa, OrgaoUnidade, Project, db
from services.etapa_responsaveis import OUTRAS_LABEL, apply_responsaveis_entries
from services.import_values import (
    parse_situacao,
    resolve_import_date,
    resolve_responsaveis_entries,
)
from services.sei_process import replace_project_sei_numbers

from routes.shared import log_project_action

from .import_csv import (
    DEFAULT_ETAPA_DESCRICAO,
    ImportOutcome,
    ParsedImportRow,
    _active_areas_by_sigla,
    _BatchContext,
    _build_imported_project,
    _filter_sei_numbers,
    _resolve_row_area,
    _resolve_row_attributes,
)

_CAMPOS_HERDADOS: tuple[str, ...] = (
    "titulo",
    "descricao",
    "status",
    "delivery_type",
    "special_project",
    "prioridade",
    "orgao",
    "area",
    "observacao",
)


@dataclass
class ParsedStage:
    """Etapa lida de uma linha do CSV, ainda com os textos crus das células."""

    descricao: str
    data_inicio: str | None = None
    data_fim: str | None = None
    responsavel: str | None = None
    situacao: str | None = None
    comentarios: str | None = None
    primeira: bool = False
    divergente: bool = False


@dataclass
class ParsedImportProject:
    """Grupo de linhas da mesma ref: campos de projeto da 1ª linha + etapas."""

    ref: str
    projeto: ParsedImportRow
    etapas: list[ParsedStage]


def _is_blank_import_row(row: ParsedImportRow) -> bool:
    """Linha sem conteúdo em nenhuma célula mapeada — descartada como ignorada."""
    for campo in fields(ParsedImportRow):
        valor = getattr(row, campo.name)
        if isinstance(valor, str) and valor.strip():
            return False
        if isinstance(valor, list) and valor:
            return False
    return True


def _stage_ref_key(row: ParsedImportRow, linha: int) -> str:
    ref = (row.ref_projeto or "").strip()
    if not ref:
        raise ValueError(
            f"Linha {linha}: ref_projeto vazio — toda linha do modo com etapas "
            "precisa da referência que agrupa o projeto."
        )
    return ref.casefold()


def _stage_from_row(
    row: ParsedImportRow, *, primeira: bool, divergente: bool = False
) -> ParsedStage:
    return ParsedStage(
        descricao=(row.etapa or "").strip(),
        data_inicio=row.etapa_data_inicio,
        data_fim=row.etapa_data_fim,
        responsavel=row.etapa_responsavel,
        situacao=row.etapa_situacao,
        comentarios=row.etapa_comentarios,
        primeira=primeira,
        divergente=divergente,
    )


def _campo_divergente(base: str | None, valor: str | None) -> bool:
    texto = (valor or "").strip()
    return bool(texto) and texto != (base or "").strip()


def _herda_com_divergencia(base: ParsedImportRow, row: ParsedImportRow) -> bool:
    """True quando a linha traz campo de projeto diferente do da 1ª linha (que vence)."""
    divergiu = any(
        _campo_divergente(getattr(base, campo), getattr(row, campo))
        for campo in _CAMPOS_HERDADOS
    )
    return divergiu or bool(row.sei_numeros and row.sei_numeros != base.sei_numeros)


def _open_stage_group(
    row: ParsedImportRow, chave: str, linha: int
) -> ParsedImportProject:
    ref = (row.ref_projeto or "").strip()
    if not row.titulo.strip():
        raise ValueError(
            f"Linha {linha}: a primeira linha do projeto {ref!r} precisa do título."
        )
    etapas = [_stage_from_row(row, primeira=True)] if (row.etapa or "").strip() else []
    return ParsedImportProject(ref=chave, projeto=row, etapas=etapas)


def _append_stage_row(
    grupo: ParsedImportProject, row: ParsedImportRow, linha: int
) -> None:
    if not (row.etapa or "").strip():
        raise ValueError(
            f"Linha {linha}: etapa vazia no projeto {grupo.ref!r} — linhas "
            "subsequentes do grupo precisam da descrição da etapa."
        )
    divergente = _herda_com_divergencia(grupo.projeto, row)
    grupo.etapas.append(_stage_from_row(row, primeira=False, divergente=divergente))


def _close_stage_group(grupo: ParsedImportProject) -> None:
    """Grupo de 1 linha sem descrição de etapa ganha a etapa placeholder."""
    if grupo.etapas:
        return
    placeholder = _stage_from_row(grupo.projeto, primeira=True)
    placeholder.descricao = DEFAULT_ETAPA_DESCRICAO
    grupo.etapas.append(placeholder)


def _ensure_ref_contigua(
    chave: str, refs_fechadas: set[str], row: ParsedImportRow, linha: int
) -> None:
    if chave not in refs_fechadas:
        return
    ref = (row.ref_projeto or "").strip()
    raise ValueError(
        f"Linha {linha}: linhas do projeto {ref!r} não são contíguas — "
        "a planilha foi reordenada?"
    )


def group_stage_rows(rows: list[ParsedImportRow]) -> list[ParsedImportProject]:
    """Agrupa as linhas do formato longo por ``ref_projeto`` (grupos contíguos).

    A 1ª linha de cada ref inicia o projeto (título obrigatório) e as seguintes
    herdam os campos de projeto dela. Ref vazia, grupo não contíguo, título
    ausente ou etapa vazia em linha subsequente levantam ``ValueError``
    apontando a linha do arquivo (o cabeçalho é a linha 1).
    """
    grupos: list[ParsedImportProject] = []
    refs_fechadas: set[str] = set()
    chave_atual: str | None = None
    for posicao, row in enumerate(rows):
        linha = row.linha or posicao + 2
        if _is_blank_import_row(row):
            continue
        chave = _stage_ref_key(row, linha)
        if chave == chave_atual:
            _append_stage_row(grupos[-1], row, linha)
            continue
        _ensure_ref_contigua(chave, refs_fechadas, row, linha)
        if chave_atual is not None:
            _close_stage_group(grupos[-1])
            refs_fechadas.add(chave_atual)
        grupos.append(_open_stage_group(row, chave, linha))
        chave_atual = chave
    if grupos:
        _close_stage_group(grupos[-1])
    return grupos


def _area_ids_por_sigla(areas_por_sigla: dict[str, OrgaoUnidade]) -> dict[str, int]:
    return {sigla: unidade.id for sigla, unidade in areas_por_sigla.items()}


def _persist_stage(
    project_id: int, ordem: int, stage: ParsedStage, area_ids: dict[str, int]
) -> bool:
    """Cria a Etapa da linha e devolve se algum valor dela caiu (ajuste)."""
    inicio, inicio_ok = resolve_import_date(stage.data_inicio)
    fim, fim_ok = resolve_import_date(stage.data_fim)
    situacao, situacao_ok = parse_situacao(stage.situacao)
    entries, responsavel_ok = resolve_responsaveis_entries(
        stage.responsavel, area_ids, OUTRAS_LABEL
    )
    etapa = Etapa(
        project_id=project_id,
        descricao=stage.descricao,
        ordem=ordem,
        iniciada=False,
        done=False,
        data_inicio=inicio,
        data_fim=fim,
        comentarios=(stage.comentarios or "").strip() or None,
    )
    db.session.add(etapa)
    if entries:
        apply_responsaveis_entries(etapa, entries)
    etapa.iniciada = situacao.iniciada
    etapa.done = situacao.done
    return not (inicio_ok and fim_ok and situacao_ok and responsavel_ok)


def _persist_group_project(
    grupo: ParsedImportProject, contexto: _BatchContext
) -> tuple[Project, bool]:
    """Cria o Project da 1ª linha do grupo; devolve (projeto, houve ajuste)."""
    area, area_ok = _resolve_row_area(
        grupo.projeto.area, contexto.areas_por_sigla, contexto.area_padrao
    )
    attrs = _resolve_row_attributes(
        grupo.projeto,
        area.sigla,
        contexto.status,
        contexto.special_project,
        contexto.delivery_type,
    )
    sei_kept, sei_dropped = _filter_sei_numbers(grupo.projeto.sei_numeros)
    project = _build_imported_project(grupo.projeto, area, attrs)
    db.session.add(project)
    db.session.flush()
    if sei_kept:
        replace_project_sei_numbers(project, sei_kept)
    log_project_action(
        project_id=project.id,
        action_type="create",
        description=f'Importou o projeto "{grupo.projeto.titulo}" via CSV',
    )
    return project, attrs.adjusted or sei_dropped > 0 or not area_ok


def _persist_stage_group(
    grupo: ParsedImportProject, contexto: _BatchContext, area_ids: dict[str, int]
) -> tuple[int, int]:
    """Persiste o grupo; devolve ``(etapas criadas, linhas com ajuste)``."""
    project, primeira_ajustada = _persist_group_project(grupo, contexto)
    ajustadas = 0
    for ordem, stage in enumerate(grupo.etapas):
        caiu = _persist_stage(project.id, ordem, stage, area_ids) or stage.divergente
        if stage.primeira:
            primeira_ajustada = primeira_ajustada or caiu
        elif caiu:
            ajustadas += 1
    return len(grupo.etapas), ajustadas + (1 if primeira_ajustada else 0)


def _persist_imported_projects_with_stages(
    rows: list[ParsedImportRow],
    orgao: OrgaoUnidade,
    default_status: str,
    default_special: str | None,
    default_delivery: str | None,
) -> ImportOutcome:
    """Agrupa e persiste o lote do modo com etapas; conta linhas ajustadas.

    O agrupamento roda antes de qualquer INSERT: ``ValueError`` de validação
    sobe sem nada gravado.
    """
    grupos = group_stage_rows(rows)
    contexto = _BatchContext(
        orgao,
        _active_areas_by_sigla(),
        default_status,
        default_special,
        default_delivery,
    )
    area_ids = _area_ids_por_sigla(contexto.areas_por_sigla)
    ignored = sum(1 for row in rows if _is_blank_import_row(row))
    imported = adjusted = etapas_criadas = 0
    for grupo in grupos:
        etapas, linhas_ajustadas = _persist_stage_group(grupo, contexto, area_ids)
        imported += 1
        etapas_criadas += etapas
        adjusted += linhas_ajustadas
    db.session.commit()
    return ImportOutcome(imported, ignored, adjusted, etapas_criadas)
