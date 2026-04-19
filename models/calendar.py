from services.token_crypto import EncryptedText
from time_utils import utc_now

from .base import db


class UserCalendarConnection(db.Model):
    __tablename__ = 'user_calendar_connection'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    provider = db.Column(db.String(30), nullable=False, default='google')
    calendar_id = db.Column(db.String(255), nullable=False, default='primary')
    access_token = db.Column(EncryptedText, nullable=True)
    refresh_token = db.Column(EncryptedText, nullable=False)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    scope = db.Column(db.String(500), nullable=True)
    google_account_id = db.Column(db.String(255), nullable=True, index=True)
    google_account_email = db.Column(db.String(255), nullable=True)
    watch_channel_id = db.Column(db.String(255), nullable=True, unique=True)
    watch_resource_id = db.Column(db.String(255), nullable=True)
    watch_expiration = db.Column(db.DateTime, nullable=True)
    watch_channel_token = db.Column(db.String(255), nullable=True)
    sync_token = db.Column(db.Text, nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = db.relationship('User', backref=db.backref('calendar_connection', uselist=False))

    def __repr__(self):
        return f'<UserCalendarConnection user={self.user_id} provider={self.provider}>'


class CalendarEvent(db.Model):
    __tablename__ = 'calendar_event'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=False)
    is_all_day = db.Column(db.Boolean, nullable=False, default=False)
    timezone = db.Column(db.String(64), nullable=False, default='America/Sao_Paulo')
    source = db.Column(db.String(20), nullable=False, default='app')
    google_calendar_id = db.Column(db.String(255), nullable=True, default='primary')
    google_event_id = db.Column(db.String(255), nullable=True)
    meet_link = db.Column(db.String(512), nullable=True)
    sync_status = db.Column(db.String(20), nullable=False, default='pending')
    sync_error = db.Column(db.Text, nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = db.relationship('User', backref='calendar_events')
    project_stage_meeting = db.relationship(
        'ProjectStageMeeting',
        back_populates='calendar_event',
        uselist=False,
    )

    __table_args__ = (
        db.UniqueConstraint('user_id', 'google_event_id', name='uq_calendar_event_user_google_event'),
        db.Index('ix_calendar_event_user_starts_at', 'user_id', 'starts_at'),
    )

    def __repr__(self):
        return f'<CalendarEvent {self.id} user={self.user_id} title={self.title}>'
