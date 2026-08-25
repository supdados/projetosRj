"""Vínculo simétrico entre projetos, armazenado uma vez com par canônico.

``ProjectRelation`` guarda "A relaciona-se com B" numa única linha com
``project_low_id < project_high_id`` — sem direção semântica e sem cascata de
estado entre os projetos. A canonicalização definitiva mora no service
(``services/project_relations.py``); o ``@validates`` aqui é reforço.
CHECK constraint não é portável SQLite/MySQL (precedente:
``models/project_collection.py``).
"""

from __future__ import annotations

from sqlalchemy.orm import validates

from time_utils import utc_now

from .base import db


class ProjectRelation(db.Model):
    """Par canônico de projetos relacionados.

    Exemplo: ``ProjectRelation(project_low_id=3, project_high_id=7,
    created_by_user_id=1)``.
    """

    __tablename__ = "project_relation"

    id = db.Column(db.Integer, primary_key=True)
    project_low_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_high_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )  # sem ondelete: histórico
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "project_low_id", "project_high_id", name="uq_project_relation_pair"
        ),
    )

    @validates("project_low_id", "project_high_id")
    def validate_par_canonico(self, key: str, value: int) -> int:
        outro = self.project_high_id if key == "project_low_id" else self.project_low_id
        if outro is None:
            return value
        low, high = (value, outro) if key == "project_low_id" else (outro, value)
        if low >= high:
            raise ValueError(
                f"par não canônico: ({low}, {high}); "
                "esperado project_low_id < project_high_id"
            )
        return value

    def __repr__(self) -> str:
        return f"<ProjectRelation {self.project_low_id}~{self.project_high_id}>"
