from time_utils import utc_now

from .base import db


class Etapa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    data_inicio = db.Column(db.Date)
    data_fim = db.Column(db.Date)
    responsavel = db.Column(db.String(100))
    iniciada = db.Column(db.Boolean, default=False, nullable=False)
    done = db.Column(db.Boolean, default=False, nullable=False)
    comentarios = db.Column(db.Text)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    entry_type = db.Column(db.String(30), nullable=False, default="manual", index=True)
    meeting = db.relationship(
        "ProjectStageMeeting",
        back_populates="etapa",
        uselist=False,
        cascade="all, delete-orphan",
    )
    responsaveis = db.relationship(
        "EtapaResponsavel",
        cascade="all, delete-orphan",
        order_by="EtapaResponsavel.ordem",
        lazy="select",
        backref="etapa",
    )

    @property
    def is_google_meeting(self):
        return self.entry_type == "google_meeting"

    def __repr__(self):
        return f"<Etapa {self.descricao[:50]}>"


class EtapaResponsavel(db.Model):
    """Área responsável por uma etapa (N:N Etapa↔OrgaoUnidade).

    area_id=None representa a opção especial "Outras áreas" (rótulo em
    services.etapa_responsaveis.OUTRAS_LABEL).
    label guarda a sigla no momento do save (fallback se o órgão sumir).
    """

    __tablename__ = "etapa_responsavel"

    id = db.Column(db.Integer, primary_key=True)
    etapa_id = db.Column(
        db.Integer,
        db.ForeignKey("etapa.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    area_id = db.Column(db.Integer, db.ForeignKey("orgao_unidade.id"), nullable=True)
    label = db.Column(db.String(255), nullable=False)
    ordem = db.Column(db.Integer, nullable=False, default=0)

    area = db.relationship("OrgaoUnidade", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("etapa_id", "area_id", name="uq_etapa_responsavel_area"),
    )

    def __repr__(self):
        return f"<EtapaResponsavel etapa={self.etapa_id} area={self.area_id} {self.label!r}>"


class ProjectStageMeeting(db.Model):
    __tablename__ = "project_stage_meeting"

    id = db.Column(db.Integer, primary_key=True)
    etapa_id = db.Column(
        db.Integer, db.ForeignKey("etapa.id"), nullable=False, unique=True, index=True
    )
    project_id = db.Column(
        db.Integer, db.ForeignKey("project.id"), nullable=False, index=True
    )
    calendar_event_id = db.Column(
        db.Integer,
        db.ForeignKey("calendar_event.id"),
        nullable=True,
        unique=True,
        index=True,
    )
    creator_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    google_owner_account_id = db.Column(db.String(255), nullable=False, index=True)
    google_owner_email = db.Column(db.String(255), nullable=True)
    google_event_id = db.Column(db.String(255), nullable=True, index=True)
    google_calendar_id = db.Column(db.String(255), nullable=True, default="primary")
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=False)
    is_all_day = db.Column(db.Boolean, nullable=False, default=False)
    timezone = db.Column(db.String(64), nullable=False, default="America/Sao_Paulo")
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    meet_link = db.Column(db.String(512), nullable=True)
    sync_status = db.Column(db.String(20), nullable=False, default="pending")
    sync_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    etapa = db.relationship("Etapa", back_populates="meeting")
    project = db.relationship("Project", back_populates="meeting_items")
    calendar_event = db.relationship(
        "CalendarEvent", back_populates="project_stage_meeting"
    )
    creator = db.relationship("User", backref="project_stage_meetings")

    __table_args__ = (
        db.Index(
            "ix_project_stage_meeting_owner_google_event",
            "google_owner_account_id",
            "google_event_id",
        ),
    )

    def __repr__(self):
        return f"<ProjectStageMeeting etapa={self.etapa_id} project={self.project_id}>"
