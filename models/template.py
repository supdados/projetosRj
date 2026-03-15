from .base import db


class StageTemplate(db.Model):
    __tablename__ = 'StageTemplate'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    items = db.relationship('StageTemplateItem', backref='template', lazy=True, cascade="all, delete-orphan", order_by="StageTemplateItem.order")

    def __repr__(self):
        return f'<StageTemplate {self.name}>'


class StageTemplateItem(db.Model):
    __tablename__ = 'StageTemplateItem'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False, default=1)
    order = db.Column(db.Integer, nullable=False)
    templateId = db.Column(db.Integer, db.ForeignKey('StageTemplate.id'), nullable=False)

    def __repr__(self):
        return f'<StageTemplateItem {self.name}>'
