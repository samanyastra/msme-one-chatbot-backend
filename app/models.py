from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "username": self.username}

# Document model extended with filename, tags and vector_ids (stores list of chunk ids)
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=True)      # optional original filename
    text = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(255), nullable=True)          # optional category/tags
    vector_ids = db.Column(db.JSON, nullable=True, default=list)  # list of vector ids for this doc
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "text": self.text,
            "tags": self.tags,
            "vector_ids": self.vector_ids or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
