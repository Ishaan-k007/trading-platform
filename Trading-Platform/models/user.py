from datetime import datetime
from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    account   = db.relationship("Account", back_populates="user", uselist=False)
    orders    = db.relationship("Order", back_populates="user")
    positions = db.relationship("Position", back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.username}>"
