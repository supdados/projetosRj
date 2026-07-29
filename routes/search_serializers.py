"""Serialização das linhas da busca global (projetos, etapas, tarefas, eventos).

Extraído de ``routes/search.py`` para manter o módulo de queries abaixo de 500
linhas. Os shapes dos itens são contrato compartilhado do dropdown do topo, da
tela ``/busca`` (SPA) e do legado ``/api/busca-global`` — não alterar chaves.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from flask import url_for

TIMEZONE_BR = ZoneInfo("America/Sao_Paulo")

_TASK_STATUS_LABELS = {
    "nao_iniciada": "Não iniciada",
    "em_andamento": "Em andamento",
    "para_validacao": "Para validação",
    "para_ajustes": "Para ajustes",
    "finalizada": "Finalizada",
}

_EVENT_SYNC_LABELS = {
    "pending": "Pendente",
    "ok": "Sincronizado",
    "error": "Erro",
}


def _truncate_text(value, max_length: int = 140) -> str:
    text_value = " ".join((value or "").split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + "..."


def _build_match_excerpt(value, term, max_length: int = 110) -> str:
    text_value = " ".join((value or "").split())
    if not text_value:
        return ""

    normalized_term = (term or "").strip().lower()
    if not normalized_term:
        return _truncate_text(text_value, max_length)

    lowered_value = text_value.lower()
    match_index = lowered_value.find(normalized_term)
    if match_index == -1:
        return _truncate_text(text_value, max_length)

    context_before = max_length // 3
    start = max(0, match_index - context_before)
    end = min(len(text_value), start + max_length)
    snippet = text_value[start:end].strip()

    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text_value):
        snippet = f"{snippet}..."
    return snippet


def _build_project_display_title(project, max_length: int = 120) -> str:
    base_title = project.titulo or f"Projeto #{project.id}"
    return _truncate_text(f"{project.id}-{base_title}", max_length)


def _to_local_datetime(utc_naive):
    if utc_naive is None:
        return None
    return utc_naive.replace(tzinfo=datetime.timezone.utc).astimezone(TIMEZONE_BR)


def _format_calendar_event_period(event) -> str:
    if not event.starts_at:
        return ""

    starts_at = _to_local_datetime(event.starts_at)
    ends_at = _to_local_datetime(event.ends_at)

    if event.is_all_day:
        display_end = starts_at.date()
        if ends_at:
            display_end = ends_at.date()
            if ends_at > starts_at and ends_at.time() == datetime.time(0, 0):
                display_end = (ends_at - datetime.timedelta(days=1)).date()
            if display_end < starts_at.date():
                display_end = starts_at.date()
        if display_end != starts_at.date():
            return f"{starts_at:%d/%m/%Y} ate {display_end:%d/%m/%Y}"
        return starts_at.strftime("%d/%m/%Y")

    if ends_at:
        if starts_at.date() == ends_at.date():
            return f"{starts_at:%d/%m/%Y} {starts_at:%H:%M} - {ends_at:%H:%M}"
        return f"{starts_at:%d/%m/%Y %H:%M} - {ends_at:%d/%m/%Y %H:%M}"

    return starts_at.strftime("%d/%m/%Y %H:%M")


def _resolve_match_info(term, ordered_fields) -> dict:
    normalized_term = (term or "").strip().lower()
    if not normalized_term:
        return {
            "match_field": "",
            "match_label": "",
            "match_excerpt": "",
        }

    for field_name, field_label, field_value in ordered_fields:
        normalized_value = " ".join((field_value or "").split())
        if not normalized_value:
            continue
        if normalized_term in normalized_value.lower():
            return {
                "match_field": field_name,
                "match_label": field_label,
                "match_excerpt": _build_match_excerpt(normalized_value, term),
            }

    return {
        "match_field": "",
        "match_label": "",
        "match_excerpt": "",
    }


def _serialize_project_rows(projects, term: str) -> list[dict]:
    return [
        {
            "type": "project",
            "type_label": "Projeto",
            "title": _truncate_text(project.titulo or f"Projeto #{project.id}", 120),
            "display_title": _build_project_display_title(project),
            "subtitle": (
                f"Órgão: {_truncate_text(project.orgao, 90)}" if project.orgao else ""
            ),
            "meta": (
                f"Área responsável: {project.orgao_ref.sigla}"
                if project.orgao_ref
                else "Área responsável não informada"
            ),
            "url": url_for("main.project_detail", project_id=project.id),
            **_resolve_match_info(
                term,
                [
                    ("titulo", "Título", project.titulo),
                    ("orgao", "Órgão", project.orgao),
                    ("short_description", "Descrição curta", project.short_description),
                    ("observacao", "Observação", project.observacao),
                ],
            ),
        }
        for project in projects
    ]


def _serialize_stage_rows(stages, term: str) -> list[dict]:
    stage_results = []
    for stage in stages:
        project = stage.project
        stage_match = _resolve_match_info(
            term,
            [
                ("descricao", "Descrição", stage.descricao),
                ("comentarios", "Comentário", stage.comentarios),
                ("responsavel", "Responsável", stage.responsavel),
            ],
        )
        stage_results.append(
            {
                "type": "stage",
                "type_label": "Etapa",
                "title": _truncate_text(stage.descricao or f"Etapa #{stage.id}", 120),
                "subtitle": (
                    f"Projeto: {_truncate_text(project.titulo, 95)}" if project else ""
                ),
                "meta": (
                    f"Responsável: {_truncate_text(stage.responsavel, 80)}"
                    if stage.responsavel
                    else "Responsável não informado"
                ),
                "url": url_for(
                    "main.project_detail",
                    project_id=stage.project_id,
                    focus_etapa=stage.id,
                ),
                **stage_match,
            }
        )
    return stage_results


def _serialize_task_rows(tasks, term: str) -> list[dict]:
    task_results = []
    for task in tasks:
        task_match = _resolve_match_info(
            term,
            [
                ("descricao", "Descrição", task.descricao),
                ("responsavel", "Responsável", task.responsavel),
                ("status", "Status", task.status),
                ("prioridade", "Prioridade", task.prioridade),
                ("tipo_pedido", "Tipo", task.tipo_pedido),
            ],
        )
        status_label = _TASK_STATUS_LABELS.get(task.status, task.status or "")
        task_meta_parts = []
        if status_label:
            task_meta_parts.append(f"Status: {status_label}")
        if task.responsavel:
            task_meta_parts.append(
                f"Responsável: {_truncate_text(task.responsavel, 80)}"
            )
        if task.prioridade:
            task_meta_parts.append(f"Prioridade: {task.prioridade}")

        task_results.append(
            {
                "type": "task",
                "type_label": "Tarefa",
                "title": _truncate_text(task.descricao or f"Tarefa #{task.id}", 120),
                "subtitle": (
                    f"Projeto: {_truncate_text(task.project.titulo, 95)}"
                    if task.project
                    else "Sem projeto"
                ),
                "meta": " | ".join(task_meta_parts),
                "url": url_for("main.task_detail", task_id=task.id),
                **task_match,
            }
        )
    return task_results


def _serialize_event_rows(events, term: str) -> list[dict]:
    event_results = []
    for event in events:
        event_match = _resolve_match_info(
            term,
            [
                ("title", "Título", event.title),
                ("description", "Descrição", event.description),
                ("location", "Local", event.location),
            ],
        )
        event_meta_parts = []
        event_period = _format_calendar_event_period(event)
        if event_period:
            event_meta_parts.append(f"Quando: {event_period}")
        if event.location:
            event_meta_parts.append(f"Local: {_truncate_text(event.location, 80)}")
        sync_label = _EVENT_SYNC_LABELS.get(event.sync_status, event.sync_status or "")
        if sync_label:
            event_meta_parts.append(f"Sync: {sync_label}")

        event_results.append(
            {
                "type": "event",
                "type_label": "Evento",
                "title": _truncate_text(event.title or f"Evento #{event.id}", 120),
                "subtitle": (
                    _truncate_text(event.description, 95) if event.description else ""
                ),
                "meta": " | ".join(event_meta_parts),
                "url": url_for("main.calendars_hub"),
                **event_match,
            }
        )
    return event_results
