"""Convite por projeto (S4/F3-2): acesso pontual que SOMA ao escopo de área.

Uma linha por par (projeto, usuário) — reativação reutiliza a mesma linha, e o
histórico completo vive em ``AutorizacaoAudit``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import validates

from time_utils import utc_now

from .base import db

ORIGEM_CONVITE = "convite"


def papeis_de_convite() -> tuple[str, ...]:
    """Papéis concedíveis por convite, do menor rank ao maior (teto: editor).

    Derivado de ``PAPEL_RANK``: gestor fica de fora porque convite nunca concede
    gestão (auto-promoção do Redmine #11075).

    Exemplo: ``papeis_de_convite() == ("leitor", "editor")``.
    """
    # Import tardio: services.authorization importa models (ciclo no topo).
    from services.authorization import PAPEL_EDITOR, PAPEL_RANK

    teto = PAPEL_RANK[PAPEL_EDITOR]
    por_rank = sorted(PAPEL_RANK.items(), key=lambda item: item[1])
    return tuple(papel for papel, rank in por_rank if rank <= teto)


class ProjectMember(db.Model):
    __tablename__ = "project_member"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    papel = db.Column(db.String(10), nullable=False)
    # Costura para vínculos futuros por grupo (origem="grupo"); v1 só usa convite.
    origem = db.Column(
        db.String(20),
        nullable=False,
        default=ORIGEM_CONVITE,
        server_default=ORIGEM_CONVITE,
    )
    granted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    project = db.relationship("Project")
    user = db.relationship("User", foreign_keys=[user_id])
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])
    revoked_by = db.relationship("User", foreign_keys=[revoked_by_id])

    __table_args__ = (
        db.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )

    @property
    def is_active(self) -> bool:
        """True enquanto o convite não foi revogado nem expirou.

        Avaliação lazy (sem cron): expirar é comparar com ``utc_now()`` na
        leitura. Ex.: ``[m for m in membros if m.is_active]``.
        """
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > utc_now()

    @validates("papel")
    def validate_papel(self, _key: str, value: str) -> str:
        """Teto rígido do convite: gestor nunca entra no banco."""
        permitidos = papeis_de_convite()
        if value in permitidos:
            return value
        esperados = "|".join(permitidos)
        raise ValueError(
            f"papel de convite inválido: {value!r}; esperado um de {esperados}"
        )

    @validates("origem")
    def validate_origem(self, _key: str, value: str) -> str:
        if value == ORIGEM_CONVITE:
            return value
        raise ValueError(
            f"origem inválida: {value!r}; esperado {ORIGEM_CONVITE!r} (v1)"
        )

    @validates("expires_at", "revoked_at")
    def validate_instante(self, _key: str, value: datetime | None) -> datetime | None:
        # Colunas DateTime guardam UTC naive; `is_active` compara com utc_now().
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def __repr__(self) -> str:
        return f"<ProjectMember project={self.project_id} user={self.user_id} {self.papel}>"
