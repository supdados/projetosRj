from collections.abc import Iterable

from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from time_utils import utc_now

from .base import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    orgao = db.Column(db.String(100), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    # Super admin = admin inicial do sistema (menor id entre os admins ativos no
    # backfill). SÓ muda por migração/DB — nenhum endpoint escreve esta coluna.
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)
    cpf_govbr = db.Column(db.String(11), unique=True, nullable=True, index=True)
    govbr_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    lockout_until = db.Column(db.DateTime, nullable=True)
    # Soft-delete (C4): None = usuário ativo; timestamp = removido. NUNCA apagamos
    # a linha — o histórico (eventos/etapas/tarefas/comentários/anexos) permanece
    # atribuído ao usuário, que passa a aparecer como "(removido)".
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    orgaos = db.relationship(
        "UserOrgao", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        """True quando o usuário não foi removido (soft-delete)."""
        return self.deleted_at is None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def needs_password_rehash(self):
        """True se o hash atual usa algoritmo legado (pré-scrypt)."""
        return not (self.password_hash or "").startswith("scrypt:")

    def set_orgaos(self, orgao_ids: Iterable[int]) -> None:
        """Substitui os vinculos em user_orgao, todos com papel `gestor`.

        Wrapper de compat de `set_orgaos_com_papeis` para chamadores que só
        conhecem ids. Ex.: `user.set_orgaos([3, 7])`.
        """
        from services.authorization import PAPEL_GESTOR

        self.set_orgaos_com_papeis((orgao_id, PAPEL_GESTOR) for orgao_id in orgao_ids)

    def set_orgaos_com_papeis(self, pares: Iterable[tuple[int, str]]) -> None:
        """Substitui os vinculos em user_orgao a partir de pares (orgao_id, papel).

        Duplicatas de `orgao_id` são ignoradas (a primeira ocorrência vence).
        Ex.: `user.set_orgaos_com_papeis([(3, "editor"), (7, "leitor")])`.
        """
        UserOrgao.query.filter_by(user_id=self.id).delete()
        seen: set[int] = set()
        for orgao_id, papel in pares:
            if orgao_id in seen:
                continue
            seen.add(orgao_id)
            db.session.add(UserOrgao(user_id=self.id, orgao_id=orgao_id, papel=papel))

    def __repr__(self):
        return f"<User {self.username}>"


class UserOrgao(db.Model):
    __tablename__ = "user_orgao"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    orgao_id = db.Column(
        db.Integer,
        db.ForeignKey("orgao_unidade.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Papel do vínculo (leitor|editor|gestor). String + validação Python em vez
    # de Enum de banco: o runner custom roda em SQLite e Postgres.
    papel = db.Column(
        db.String(10), nullable=False, default="gestor", server_default="gestor"
    )

    orgao = db.relationship("OrgaoUnidade")

    __table_args__ = (
        db.UniqueConstraint("user_id", "orgao_id", name="uq_user_orgao_user_orgao"),
        db.Index("ix_user_orgao_user_id", "user_id"),
        db.Index("ix_user_orgao_orgao_id", "orgao_id"),
    )

    @validates("papel")
    def validate_papel(self, _key: str, value: str) -> str:
        """Rejeita papel fora da taxonomia. Ex.: `UserOrgao(papel="editor")`."""
        # Import tardio: services.authorization importa models (ciclo no topo).
        from services.authorization import PAPEL_RANK

        if value in PAPEL_RANK:
            return value
        esperados = "|".join(PAPEL_RANK)
        raise ValueError(f"papel inválido: {value!r}; esperado um de {esperados}")

    def __repr__(self):
        return f"<UserOrgao user_id={self.user_id} orgao_id={self.orgao_id}>"


class UserNotification(db.Model):
    __tablename__ = "user_notification"

    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    actor_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True, index=True
    )
    event_type = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)

    recipient = db.relationship(
        "User", foreign_keys=[recipient_user_id], backref="received_notifications"
    )
    actor = db.relationship(
        "User", foreign_keys=[actor_user_id], backref="sent_notifications"
    )

    __table_args__ = (
        db.Index(
            "ix_user_notification_recipient_read_created",
            "recipient_user_id",
            "is_read",
            "created_at",
        ),
    )

    def __repr__(self):
        return f"<UserNotification {self.event_type} to user {self.recipient_user_id}>"
