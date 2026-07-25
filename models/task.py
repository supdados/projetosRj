from sqlalchemy import event

from time_utils import utc_now

from .base import TaskItemQuery, TaskQuery, db
from .etapa import Etapa


def _resolve_legacy_kwargs(kwargs: dict) -> None:
    """Normaliza kwargs legados (titulo→descricao, task_id→anchor) in-place.

    Exemplo: Task(titulo='foo', task_id=3) cria uma subtarefa herdando project/ordem do task 3.
    """
    legacy_titulo = kwargs.pop("titulo", None)
    legacy_task_id = kwargs.pop("task_id", None)

    if legacy_titulo is not None and "descricao" not in kwargs:
        kwargs["descricao"] = legacy_titulo

    if legacy_task_id is None:
        return

    try:
        anchor_id = int(legacy_task_id)
    except (TypeError, ValueError):
        return

    anchor = db.session.get(Task, anchor_id)
    if anchor is None:
        return

    kwargs.setdefault("project_id", anchor.project_id)
    kwargs.setdefault("legacy_parent_task_id", anchor.id)
    kwargs.setdefault("created_by_id", anchor.created_by_id)

    if "ordem" not in kwargs:
        next_ordem = (
            db.session.query(db.func.max(Task.ordem))
            .filter(Task.project_id == anchor.project_id, Task.is_archived.is_(False))
            .scalar()
            or 0
        )
        kwargs["ordem"] = next_ordem + 1


class Task(db.Model):
    __tablename__ = "task"
    query_class = TaskQuery
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="nao_iniciada")
    responsavel = db.Column(db.String(100), nullable=True)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    # Tarefas criadas após a migração v4.5 nascem ligadas a uma etapa.
    # Legadas continuam com etapa_id NULL; o usuário pode reassociá-las.
    etapa_id = db.Column(
        db.Integer,
        db.ForeignKey("etapa.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    legacy_parent_task_id = db.Column(
        db.Integer, db.ForeignKey("task.id"), nullable=True
    )
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    prioridade = db.Column(db.String(20), nullable=True)
    tipo_pedido = db.Column(db.String(30), nullable=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    archived_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship("Project", backref=db.backref("tasks", lazy=True))
    etapa = db.relationship("Etapa", backref=db.backref("etapa_tasks", lazy="dynamic"))
    created_by = db.relationship("User", backref="created_tasks")
    comments = db.relationship(
        "TaskComment",
        backref="task",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="TaskComment.created_at",
    )
    anexos = db.relationship(
        "TaskAnexo",
        backref="task",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="TaskAnexo.created_at",
    )
    # Responsáveis múltiplos (N:N via task_assignee). selectin evita N+1 ao
    # serializar a lista do hub. A coluna legada ``responsavel`` (texto) deixa
    # de ser usada para novas atribuições.
    assignees = db.relationship(
        "TaskAssignee",
        backref="task_ref",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="TaskAssignee.created_at",
    )

    def __init__(self, **kwargs):
        _resolve_legacy_kwargs(kwargs)
        kwargs.setdefault("status", "nao_iniciada")
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Task {self.descricao[:50]}>"

    # Mantidos porque templates e rotas legadas ainda referenciam esses nomes.

    @property
    def titulo(self):
        return self.descricao

    @titulo.setter
    def titulo(self, value):
        self.descricao = value

    @property
    def is_finalized(self):
        return self.is_archived

    @is_finalized.setter
    def is_finalized(self, value):
        self.is_archived = bool(value)

    @property
    def finalized_at(self):
        return self.archived_at

    @finalized_at.setter
    def finalized_at(self, value):
        self.archived_at = value

    @property
    def task_id(self):
        return self.id

    @task_id.setter
    def task_id(self, value):
        try:
            anchor_id = int(value)
        except (TypeError, ValueError):
            return
        anchor = db.session.get(Task, anchor_id)
        if not anchor:
            return
        self.project_id = anchor.project_id
        self.legacy_parent_task_id = anchor.id
        if not self.created_by_id:
            self.created_by_id = anchor.created_by_id

    @property
    def task(self):
        return self

    @property
    def items(self):
        return [self]


class TaskAssignee(db.Model):
    """Atribuição N:N entre Task e User — múltiplos responsáveis por tarefa.

    Exemplo: TaskAssignee(task_id=10, user_id=3) marca o usuário 3 como
    responsável da tarefa 10. PK composta garante idempotência.
    """

    __tablename__ = "task_assignee"

    task_id = db.Column(
        db.Integer,
        db.ForeignKey("task.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship("User")

    __table_args__ = (db.Index("ix_task_assignee_user_id", "user_id"),)

    def __repr__(self):
        return f"<TaskAssignee task_id={self.task_id} user_id={self.user_id}>"


@event.listens_for(Etapa, "before_delete")
def _clear_task_stage_refs_before_etapa_delete(mapper, connection, target):
    connection.execute(
        Task.__table__.update().where(Task.etapa_id == target.id).values(etapa_id=None)
    )


class TaskItem(db.Model):
    # Maps to the same table as Task; TaskItemQuery.count() scopes to child rows only.
    __table__ = Task.__table__
    query_class = TaskItemQuery

    def __init__(self, **kwargs):
        _resolve_legacy_kwargs(kwargs)
        kwargs.setdefault("status", "nao_iniciada")
        super().__init__(**kwargs)

    # Reuse property descriptors from Task — avoids duplicating all alias definitions.
    titulo = Task.titulo
    is_finalized = Task.is_finalized
    finalized_at = Task.finalized_at
    task_id = Task.task_id
    task = Task.task
    items = Task.items


class TaskAnexo(db.Model):
    __tablename__ = "task_anexo"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    uploaded_by = db.relationship("User", backref="task_anexos")

    @property
    def task_item(self):
        return self.task

    @property
    def task_item_id(self):
        return self.task_id

    def __repr__(self):
        return f"<TaskAnexo {self.filename}>"


class TaskComment(db.Model):
    __tablename__ = "task_comment"
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=utc_now, nullable=True)

    author = db.relationship("User", backref="task_comments")

    @property
    def task_item(self):
        return self.task

    @property
    def task_item_id(self):
        return self.task_id

    @task_item_id.setter
    def task_item_id(self, value):
        self.task_id = value

    def __repr__(self):
        return f"<TaskComment {self.id} by user {self.user_id}>"


class TaskAccessAudit(db.Model):
    __tablename__ = "task_access_audit"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    actor_user_id = db.Column(db.Integer, nullable=False, index=True)
    actor_name = db.Column(db.String(100), nullable=False)
    task_author_user_id = db.Column(db.Integer, nullable=True, index=True)
    action_type = db.Column(db.String(50), nullable=False, index=True)
    reason = db.Column(db.String(120), nullable=False)
    attempted_status = db.Column(db.String(20), nullable=True)
    task_description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    def __repr__(self):
        return f"<TaskAccessAudit {self.action_type} task={self.task_id} actor={self.actor_user_id}>"


class LegacyTaskRedirect(db.Model):
    __tablename__ = "legacy_task_redirect"
    id = db.Column(db.Integer, primary_key=True)
    legacy_task_id = db.Column(db.Integer, nullable=False, index=True, unique=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    sample_task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    project = db.relationship("Project", backref="legacy_task_redirects")
    sample_task = db.relationship("Task", backref="legacy_redirect_sources")


# Aliases de compatibilidade para rotas legadas (/tarefas/itens/...).
TaskItemComment = TaskComment
TaskItemAnexo = TaskAnexo
