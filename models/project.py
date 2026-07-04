from time_utils import utc_now

from .base import db


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    orgao = db.Column(db.String(100))
    orgao_id = db.Column(
        db.Integer,
        db.ForeignKey("orgao_unidade.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    orgao_ref = db.relationship("OrgaoUnidade")
    prioridade = db.Column(db.String(20))
    status = db.Column(db.String(20), default="Vigente", nullable=False)
    observacao = db.Column(db.Text)
    objetivo_id = db.Column(db.Integer, db.ForeignKey("objetivo.id"), nullable=True)
    resultado_esperado_id = db.Column(
        db.Integer, db.ForeignKey("resultado_esperado.id"), nullable=True
    )

    special_project = db.Column(db.String(20), nullable=True)
    # Espelho do 1º número de project_sei_process (expand-contract, 1 release):
    # mantém rollback/instância antiga funcionando; o backfill reconcilia no boot.
    sei_process = db.Column(db.String(50), nullable=True)
    short_description = db.Column(db.Text, nullable=True)
    delivery_type = db.Column(db.String(50), nullable=True)
    abep_indicator = db.Column(db.String(255), nullable=True)
    github_link = db.Column(db.String(500), nullable=True)
    documentation_link = db.Column(db.String(500), nullable=True)
    product_link = db.Column(db.String(500), nullable=True)

    etapas = db.relationship(
        "Etapa",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Etapa.ordem",
    )
    meeting_items = db.relationship(
        "ProjectStageMeeting",
        back_populates="project",
        lazy=True,
        cascade="all, delete-orphan",
    )
    objetivo = db.relationship("Objetivo", backref="projetos")
    resultado_esperado = db.relationship("ResultadoEsperado", backref="projetos")
    indicadores = db.relationship(
        "IndicadorProjeto", backref="project", lazy=True, cascade="all, delete-orphan"
    )
    sei_processes = db.relationship(
        "ProjectSeiProcess",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ProjectSeiProcess.ordem",
    )

    @property
    def data_inicio_projeto(self):
        if not self.etapas:
            return None
        datas_inicio_etapas = [
            etapa.data_inicio for etapa in self.etapas if etapa.data_inicio
        ]
        return min(datas_inicio_etapas) if datas_inicio_etapas else None

    @property
    def data_fim_projeto(self):
        if not self.etapas:
            return None
        datas_fim_etapas = [etapa.data_fim for etapa in self.etapas if etapa.data_fim]
        return max(datas_fim_etapas) if datas_fim_etapas else None

    @property
    def todas_etapas_concluidas(self):
        workflow_etapas = self.workflow_etapas
        if not workflow_etapas:
            return False
        return all(etapa.iniciada and etapa.done for etapa in workflow_etapas)

    @property
    def workflow_etapas(self):
        return [etapa for etapa in self.etapas if etapa.entry_type != "google_meeting"]

    @property
    def total_workflow_etapas(self):
        return len(self.workflow_etapas)

    @property
    def etapas_concluidas(self):
        return sum(1 for etapa in self.workflow_etapas if etapa.iniciada and etapa.done)

    def __repr__(self):
        return f"<Project {self.titulo}>"


class ProjectSeiProcess(db.Model):
    __tablename__ = "project_sei_process"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("project.id"), nullable=False, index=True
    )
    numero = db.Column(db.String(50), nullable=False)
    ordem = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("project_id", "numero", name="uq_project_sei_numero"),
    )

    def __repr__(self):
        return f"<ProjectSeiProcess {self.numero} (project {self.project_id})>"


class ProjectHistory(db.Model):
    __tablename__ = "project_history"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    action_description = db.Column(db.Text, nullable=False)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=utc_now, nullable=False)

    project = db.relationship(
        "Project", backref=db.backref("history", cascade="all, delete-orphan")
    )
    user = db.relationship("User", backref="project_actions")

    def __repr__(self):
        return f"<ProjectHistory {self.action_type} by user {self.user_id} at {self.timestamp}>"
