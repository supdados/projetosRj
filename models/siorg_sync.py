from time_utils import utc_now

from .base import db

SIORG_SYNC_STATUSES = ("em_andamento", "sucesso", "erro")


class SiorgSyncLog(db.Model):
    __tablename__ = "siorg_sync_log"

    id = db.Column(db.Integer, primary_key=True)
    iniciado_em = db.Column(db.DateTime, nullable=False, default=utc_now)
    finalizado_em = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="em_andamento")
    codigo_raiz = db.Column(db.Integer, nullable=True)
    versao_global = db.Column(db.String(80), nullable=True)
    hash_manifesto = db.Column(db.String(128), nullable=True)
    criadas = db.Column(db.Integer, nullable=False, default=0)
    atualizadas = db.Column(db.Integer, nullable=False, default=0)
    desativadas = db.Column(db.Integer, nullable=False, default=0)
    erro = db.Column(db.Text, nullable=True)
    disparado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )

    disparado_por = db.relationship("User", lazy="joined")

    __table_args__ = (db.Index("ix_siorg_sync_log_iniciado_em", "iniciado_em"),)

    def __repr__(self) -> str:
        return f"<SiorgSyncLog {self.id} {self.status}>"
