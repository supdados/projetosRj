from time_utils import utc_now

from .base import db

CADERNO_BLOCK_TYPES = {"text", "nota", "project", "etapa", "tarefa"}
MAX_CADERNO_EXPAND_STEPS = 3


class CadernoBlock(db.Model):
    __tablename__ = "caderno_block"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    block_type = db.Column(db.String(20), nullable=False, default="text")
    content = db.Column(db.Text, nullable=True)
    reference_id = db.Column(db.Integer, nullable=True)
    position = db.Column(db.Float, nullable=False, default=0.0, index=True)
    grid_x = db.Column(db.Integer, nullable=False, default=0)
    grid_y = db.Column(db.Integer, nullable=False, default=0)
    grid_w = db.Column(db.Integer, nullable=False, default=6)
    grid_h = db.Column(db.Integer, nullable=False, default=5)
    attached_to_block_id = db.Column(db.Integer, nullable=True, index=True)
    attached_offset_x = db.Column(db.Integer, nullable=False, default=0)
    attached_offset_y = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user = db.relationship(
        "User",
        backref=db.backref("caderno_blocks", lazy=True, cascade="all, delete-orphan"),
    )

    def __repr__(self):
        return f"<CadernoBlock {self.block_type} user={self.user_id}>"


class CadernoState(db.Model):
    __tablename__ = "caderno_state"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True, index=True
    )
    expand_steps = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "caderno_state", uselist=False, cascade="all, delete-orphan"
        ),
    )

    def __repr__(self):
        return f"<CadernoState user={self.user_id} expand_steps={self.expand_steps}>"
