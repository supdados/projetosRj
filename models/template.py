from time_utils import utc_now

from .base import db


class StageTemplate(db.Model):
    __tablename__ = "StageTemplate"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=True)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=True
    )
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    items = db.relationship(
        "StageTemplateItem",
        backref="template",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="StageTemplateItem.order",
    )
    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="joined")
    updated_by = db.relationship("User", foreign_keys=[updated_by_id], lazy="joined")
    usages = db.relationship(
        "StageTemplateUsage",
        backref="template",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<StageTemplate {self.name}>"


class StageTemplateItem(db.Model):
    __tablename__ = "StageTemplateItem"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False, default=1)
    order = db.Column(db.Integer, nullable=False)
    templateId = db.Column(
        db.Integer, db.ForeignKey("StageTemplate.id"), nullable=False
    )

    def __repr__(self):
        return f"<StageTemplateItem {self.name}>"


class StageTemplateUsage(db.Model):
    __tablename__ = "stage_template_usage"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("StageTemplate.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    source = db.Column(db.String(16), nullable=False)

    __table_args__ = (
        db.Index(
            "ix_stage_template_usage_template_project", "template_id", "project_id"
        ),
    )

    def __repr__(self):
        return f"<StageTemplateUsage template={self.template_id} project={self.project_id} source={self.source}>"
