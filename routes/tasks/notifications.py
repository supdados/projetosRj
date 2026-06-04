"""Emissores de notificação para eventos de Task.

Cada função representa um evento de domínio (criação, edição, arquivamento…).
Centraliza a construção da mensagem e o chamado de ``notify_task_event`` para
evitar duplicação nas rotas.

Todas leem ``g.user`` para identificar o ator.
"""

from flask import g, url_for

from routes.tasks.constants import _preview_text, _task_status_label
from routes.tasks.queries import _task_active_target_url
from services.notifications import (
    create_user_notifications,
    notify_task_assignment_change,
    notify_task_event,
)
from services.task_mutation import TaskEditDiff


def notify_assignee_change(task, added_user_ids, removed_user_ids) -> None:
    """Notifica (sino) quem foi adicionado/removido como responsável da tarefa.

    Dispara em TODA atribuição (tarefa nova ou edição). ``create_user_notifications``
    já descarta o próprio ator e valida a existência dos usuários, então é seguro
    passar listas que incluam o ator. Sem e-mail (não há infra).

    Uso: notify_assignee_change(task, added_ids, removed_ids) após reconciliar.
    """
    if not added_user_ids and not removed_user_ids:
        return
    target_url = _task_active_target_url(task)
    descricao = _preview_text(task.descricao, 90)
    if added_user_ids:
        create_user_notifications(
            added_user_ids,
            g.user.id,
            "task_assigned",
            "Você foi atribuído a uma tarefa",
            f'{g.user.name} atribuiu você à tarefa "{descricao}".',
            target_url,
        )
    if removed_user_ids:
        create_user_notifications(
            removed_user_ids,
            g.user.id,
            "task_unassigned",
            "Você foi removido de uma tarefa",
            f'{g.user.name} removeu você da tarefa "{descricao}".',
            target_url,
        )


def notify_task_created(task) -> None:
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_created",
        title="Nova tarefa",
        message=(
            f'{g.user.name} criou a tarefa "{_preview_text(task.descricao, 90)}" '
            f"com status {_task_status_label(task.status)}."
        ),
    )
    if task.responsavel:
        notify_task_assignment_change(
            task,
            task,
            g.user.id,
            old_responsavel=None,
            new_responsavel=task.responsavel,
        )


def notify_task_edited(task, diff: TaskEditDiff) -> None:
    """Emite 'task_updated' com sumário das mudanças + reassignment se houve."""
    changes = _edit_change_descriptions(task, diff)
    if changes:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type="task_updated",
            title="Tarefa atualizada",
            message=(
                f'{g.user.name} atualizou "{_preview_text(task.descricao, 90)}": '
                f'{", ".join(changes)}.'
            ),
        )

    if (diff.old_responsavel or "") != (task.responsavel or ""):
        notify_task_assignment_change(
            task,
            task,
            g.user.id,
            old_responsavel=diff.old_responsavel,
            new_responsavel=task.responsavel,
        )


def _edit_change_descriptions(task, diff: TaskEditDiff) -> list[str]:
    changes: list[str] = []
    if diff.old_descricao != task.descricao:
        changes.append("descrição")
    if diff.old_status != task.status:
        changes.append(f"status para {_task_status_label(task.status)}")
    if diff.old_prioridade != task.prioridade:
        changes.append(f'prioridade para "{task.prioridade or "vazio"}"')
    if diff.old_tipo != task.tipo_pedido:
        changes.append(f'tipo para "{task.tipo_pedido or "vazio"}"')
    if diff.old_project_id != task.project_id:
        changes.append("projeto")
    return changes


def notify_status_change(task, old_status: str) -> None:
    if old_status == task.status:
        return
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_status_updated",
        title="Status atualizado",
        message=(
            f"{g.user.name} alterou o status da tarefa "
            f'"{_preview_text(task.descricao, 90)}" '
            f"de {_task_status_label(old_status)} para {_task_status_label(task.status)}."
        ),
    )


def notify_prioridade_change(task, old_prioridade: str | None) -> None:
    if old_prioridade == task.prioridade:
        return
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_priority_updated",
        title="Prioridade atualizada",
        message=(
            f"{g.user.name} alterou a prioridade da tarefa "
            f'"{_preview_text(task.descricao, 90)}" '
            f'de "{old_prioridade or "vazio"}" para "{task.prioridade or "vazio"}".'
        ),
    )


def notify_tipo_change(task, old_tipo: str | None) -> None:
    if old_tipo == task.tipo_pedido:
        return
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_type_updated",
        title="Tipo atualizado",
        message=(
            f"{g.user.name} alterou o tipo da tarefa "
            f'"{_preview_text(task.descricao, 90)}" '
            f'de "{old_tipo or "vazio"}" para "{task.tipo_pedido or "vazio"}".'
        ),
    )


def notify_task_finalized(task) -> None:
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_finalized",
        title="Tarefa finalizada",
        message=f'{g.user.name} finalizou a tarefa "{_preview_text(task.descricao, 90)}".',
        target_url=_task_active_target_url(task),
    )


def notify_task_unarchived(task) -> None:
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_unarchived",
        title="Tarefa desarquivada",
        message=f'{g.user.name} desarquivou "{_preview_text(task.descricao, 90)}".',
        target_url=url_for("main.list_tasks"),
    )


def notify_task_deleted(task) -> None:
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_deleted",
        title="Tarefa excluída",
        message=f'{g.user.name} excluiu "{_preview_text(task.descricao, 90)}".',
        target_url=url_for("main.list_tasks"),
    )


def notify_task_archived_in_batch(task) -> None:
    notify_task_event(
        task,
        actor_user_id=g.user.id,
        event_type="task_archived",
        title="Tarefa arquivada",
        message=f'{g.user.name} arquivou a tarefa "{_preview_text(task.descricao, 90)}".',
        target_url=url_for("main.list_tasks_archived"),
    )
