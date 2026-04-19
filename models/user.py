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
    cpf_govbr = db.Column(db.String(11), unique=True, nullable=True, index=True)
    govbr_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    lockout_until = db.Column(db.DateTime, nullable=True)

    # Relacionamento com multiplas areas
    areas = db.relationship('UserArea', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='scrypt')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def needs_password_rehash(self):
        """True se o hash atual usa algoritmo legado (pré-scrypt)."""
        return not (self.password_hash or '').startswith('scrypt:')

    def get_areas(self):
        return [ua.area for ua in self.areas]

    def has_access_to_area(self, area):
        if self.is_admin:
            return True
        return area in self.get_areas()

    def set_areas(self, area_list):
        UserArea.query.filter_by(user_id=self.id).delete()
        for area in area_list:
            if area:
                user_area = UserArea(user_id=self.id, area=area)
                db.session.add(user_area)

    def __repr__(self):
        return f'<User {self.username}>'


class UserArea(db.Model):
    __tablename__ = 'user_areas'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    area = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<UserArea user_id={self.user_id} area={self.area}>'


class AreaCatalog(db.Model):
    __tablename__ = 'area_catalog'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    def __repr__(self):
        return f'<AreaCatalog {self.name}>'


class UserNotification(db.Model):
    __tablename__ = 'user_notification'

    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)

    recipient = db.relationship('User', foreign_keys=[recipient_user_id], backref='received_notifications')
    actor = db.relationship('User', foreign_keys=[actor_user_id], backref='sent_notifications')

    __table_args__ = (
        db.Index(
            'ix_user_notification_recipient_read_created',
            'recipient_user_id',
            'is_read',
            'created_at',
        ),
    )

    def __repr__(self):
        return f'<UserNotification {self.event_type} to user {self.recipient_user_id}>'
