"""Extração e coerção de inputs para rotas de Task (PUT/POST com form+JSON).

Não depende de ``request`` global: recebe form e payload como parâmetros, o que
facilita testar com dicts simulados.
"""

from dataclasses import dataclass

from routes.tasks.constants import (
    LEGACY_TIPOS,
    VALID_PRIORIDADES,
    VALID_STATUSES,
    VALID_TIPOS,
)


@dataclass
class EditInputs:
    """Valores extraídos e coagidos do request para edição de Task."""

    descricao: str
    status: str
    responsavel_raw: str
    prioridade: str | None
    tipo_pedido: str | None
    project_raw: str | None


def _first_non_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _coerce_tipo(raw: str | None, current_tipo: str | None) -> str | None:
    """Valor inválido vira ``None``; legado preservado apenas se a tarefa já era legada.

    Why: clientes antigos ainda podem enviar tipos legados; não queremos forçar
    migração até terem atualizado o formulário.
    """
    if raw is None:
        return None
    if raw in VALID_TIPOS:
        return raw
    if raw in LEGACY_TIPOS and current_tipo in LEGACY_TIPOS:
        return current_tipo
    return None


def extract_edit_inputs(task, form, payload) -> EditInputs:
    """Lê form + payload JSON e devolve inputs com fallback para o valor atual da tarefa.

    Regra: se a chave não está nem em ``form`` nem em ``payload``, o campo mantém
    o valor atual da ``task`` (edição parcial). Se está e é inválido, vira o
    fallback mais "seguro" (status atual, prioridade None, etc).
    """
    descricao = _first_non_none(
        form.get("descricao"),
        payload.get("descricao"),
        form.get("titulo"),
        payload.get("titulo"),
        task.descricao,
    )
    descricao = (descricao or "").strip()

    status = _first_non_none(form.get("status"), payload.get("status"), task.status)
    status = (status or "").strip()
    if status not in VALID_STATUSES:
        status = task.status

    project_raw = _first_non_none(
        form.get("project"),
        form.get("project_id"),
        payload.get("project"),
        payload.get("project_id"),
    )

    has_responsavel = "responsavel" in form or "responsavel" in payload
    responsavel_raw = (
        (form.get("responsavel") or payload.get("responsavel") or "").strip()
        if has_responsavel
        else (task.responsavel or "")
    )

    has_prioridade = "prioridade" in form or "prioridade" in payload
    if has_prioridade:
        raw = (
            form.get("prioridade") or payload.get("prioridade") or ""
        ).strip() or None
        prioridade = raw if raw in VALID_PRIORIDADES else None
    else:
        prioridade = task.prioridade

    has_tipo = "tipo_pedido" in form or "tipo_pedido" in payload
    if has_tipo:
        raw = (
            form.get("tipo_pedido") or payload.get("tipo_pedido") or ""
        ).strip() or None
        tipo_pedido = _coerce_tipo(raw, task.tipo_pedido)
    else:
        tipo_pedido = task.tipo_pedido

    return EditInputs(
        descricao=descricao,
        status=status,
        responsavel_raw=responsavel_raw,
        prioridade=prioridade,
        tipo_pedido=tipo_pedido,
        project_raw=project_raw,
    )
