"""Criação de tarefa usada por ``POST /api/tarefas``.

Resolve projeto/etapa/responsável com os MESMOS helpers de
``routes/tasks/creation.py`` (mensagens e status do contrato HTTP preservados),
normaliza status/prioridade/tipo e monta ``Task`` + responsáveis N:N +
notificações de criação.

NÃO faz commit nem toca ``flask.request``/``Response``: a casca (``api_tarefa_criar``)
lê o corpo JSON, traduz ``TaskCreationRefusal`` para o envelope ``fail`` e commita.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from models import Task, db
from routes.tasks.constants import (
    VALID_PRIORIDADES,
    VALID_STATUSES,
    VALID_TIPOS,
    _preview_text,
    _task_status_label,
)
from routes.tasks.creation import (
    _format_invalid_responsavel_message,
    _get_assignable_users_for_project,
    _resolve_etapa_token,
    _resolve_project_token,
    _validate_task_responsavel,
)
from routes.tasks.notifications import notify_assignee_change
from routes.tasks.queries import set_task_assignees
from services.notifications import notify_task_assignment_change, notify_task_event

DEFAULT_TASK_STATUS = "nao_iniciada"


@dataclass(frozen=True)
class TaskCreationRefusal:
    """Recusa de validação já traduzida para o envelope HTTP (mensagem/status/code)."""

    message: str
    status: int
    code: str


@dataclass
class TaskCreationInput:
    """Campos normalizados e já validados para criar uma tarefa."""

    descricao: str
    project: Any = None
    etapa: Any = None
    status: str = DEFAULT_TASK_STATUS
    responsavel: str | None = None
    prioridade: str | None = None
    tipo_pedido: str | None = None
    assignee_ids: list[int] = field(default_factory=list)


def resolve_task_creation(
    body: Mapping[str, Any],
) -> tuple[TaskCreationInput | None, TaskCreationRefusal | None]:
    """Valida o corpo do quick-add/composer e devolve ``(input, refusal)``.

    Ordem de recusa preservada do endpoint original: projeto, etapa, descrição e
    responsável. Campos de enum inválidos NÃO recusam — caem no default.

    Exemplo:
        >>> data, refusal = resolve_task_creation({"descricao": "Avulsa"})
    """
    project, refusal = _resolve_project(body)
    if refusal is not None:
        return None, refusal

    etapa, refusal = _resolve_etapa(body, project)
    if refusal is not None:
        return None, refusal

    descricao = (body.get("descricao") or body.get("titulo") or "").strip()
    if not descricao:
        return None, TaskCreationRefusal("Descrição é obrigatória.", 422, "validation")

    responsavel, refusal = _resolve_responsavel(body, project)
    if refusal is not None:
        return None, refusal

    return _build_input(body, project, etapa, descricao, responsavel), None


def create_task_record(data: TaskCreationInput, *, author: Any) -> Task:
    """Cria a ``Task`` + responsáveis N:N + notificações, SEM commit.

    Args:
        data: Saída de ``resolve_task_creation`` (já validada).
        author: Usuário criador (``g.user`` na rota).

    Returns:
        A ``Task`` recém-adicionada à sessão (com ``flush`` para obter ``id``).

    Exemplo:
        >>> task = create_task_record(data, author=g.user)
        >>> db.session.commit()
    """
    project_id = data.project.id if data.project else None
    task = Task(
        descricao=data.descricao,
        status=data.status,
        responsavel=data.responsavel or None,
        prioridade=data.prioridade,
        tipo_pedido=data.tipo_pedido,
        project_id=project_id,
        etapa_id=data.etapa.id if data.etapa else None,
        created_by_id=author.id,
        ordem=_next_task_ordem(project_id) + 1,
    )
    db.session.add(task)
    db.session.flush()

    added, removed = set_task_assignees(task, _allowed_assignee_ids(data))
    _notify_task_created(task, author=author, added=added, removed=removed)
    return task


def _resolve_project(body: Mapping[str, Any]) -> tuple[Any, TaskCreationRefusal | None]:
    """Resolve ``project``/``project_id`` exigindo rank >= editor no projeto."""
    project, error, status = _resolve_project_token(
        _token_value(body, "project", "project_id"), allow_empty=True, for_write=True
    )
    if error:
        return None, TaskCreationRefusal(error, status, _refusal_code(status))
    return project, None


def _resolve_etapa(
    body: Mapping[str, Any], project: Any
) -> tuple[Any, TaskCreationRefusal | None]:
    """Resolve ``etapa``/``etapa_id`` dentro do projeto informado."""
    etapa, error, status = _resolve_etapa_token(
        _token_value(body, "etapa", "etapa_id"), project, allow_empty=True
    )
    if error:
        return None, TaskCreationRefusal(error, status, _refusal_code(status))
    return etapa, None


def _resolve_responsavel(
    body: Mapping[str, Any], project: Any
) -> tuple[str, TaskCreationRefusal | None]:
    """Canoniza os nomes de ``responsavel`` contra quem pode ser atribuído."""
    is_valid, canonical, invalid_names = _validate_task_responsavel(
        project, (body.get("responsavel") or "").strip()
    )
    if not is_valid:
        message = _format_invalid_responsavel_message(invalid_names)
        return "", TaskCreationRefusal(message, 422, "validation")
    return canonical, None


def _build_input(
    body: Mapping[str, Any],
    project: Any,
    etapa: Any,
    descricao: str,
    responsavel: str,
) -> TaskCreationInput:
    """Monta o input com os enums normalizados (valor inválido cai no default)."""
    return TaskCreationInput(
        descricao=descricao,
        project=project,
        etapa=etapa,
        status=_normalized_choice(body.get("status"), VALID_STATUSES)
        or DEFAULT_TASK_STATUS,
        responsavel=responsavel or None,
        prioridade=_normalized_choice(body.get("prioridade"), VALID_PRIORIDADES),
        tipo_pedido=_normalized_choice(body.get("tipo_pedido"), VALID_TIPOS),
        assignee_ids=_parse_assignee_ids(body.get("assignee_ids")),
    )


def _token_value(body: Mapping[str, Any], key: str, alias: str) -> Any:
    """Lê ``key`` aceitando o alias ``*_id`` que a SPA envia."""
    value = body.get(key)
    if value is None:
        return body.get(alias)
    return value


def _refusal_code(status: int) -> str:
    """Traduz o status dos resolvers legados para o ``code`` do envelope."""
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    return "validation"


def _normalized_choice(raw: Any, valid: Any) -> str | None:
    """Devolve o valor apenas quando pertence ao conjunto permitido."""
    value = (raw or "").strip()
    if value not in valid:
        return None
    return value


def _parse_assignee_ids(raw: Any) -> list[int]:
    """Converte a lista de ids do corpo, descartando o que não for inteiro."""
    if not isinstance(raw, list):
        return []
    parsed: list[int] = []
    for value in raw:
        try:
            parsed.append(int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _allowed_assignee_ids(data: TaskCreationInput) -> list[int]:
    """Filtra os responsáveis N:N pelos usuários com acesso ao projeto."""
    allowed = {user.id for user in _get_assignable_users_for_project(data.project)}
    return [uid for uid in data.assignee_ids if uid in allowed]


def _next_task_ordem(project_id: int | None) -> int:
    """Maior ``ordem`` entre as tarefas não arquivadas do projeto (0 se vazio)."""
    return (
        db.session.query(db.func.max(Task.ordem))
        .filter(Task.project_id == project_id, Task.is_archived.is_(False))
        .scalar()
        or 0
    )


def _notify_task_created(
    task: Task, *, author: Any, added: list[int], removed: list[int]
) -> None:
    """Dispara os eventos de criação (feed, responsável textual e N:N)."""
    notify_task_event(
        task,
        actor_user_id=author.id,
        event_type="task_created",
        title="Nova tarefa",
        message=(
            f'{author.name} criou a tarefa "{_preview_text(task.descricao, 90)}" '
            f"com status {_task_status_label(task.status)}."
        ),
    )
    if task.responsavel:
        notify_task_assignment_change(
            task,
            task,
            author.id,
            old_responsavel=None,
            new_responsavel=task.responsavel,
        )
    notify_assignee_change(task, added, removed)
