from datetime import datetime
from decimal import Decimal
from extensions import db


class Position(db.Model):
    __tablename__ = "positions"
    __table_args__ = (db.UniqueConstraint("user_id", "symbol", name="uq_position"),)

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    symbol        = db.Column(db.String(10), nullable=False)
    quantity      = db.Column(db.Numeric(18, 6), nullable=False, default=Decimal("0"))
    average_price = db.Column(db.Numeric(18, 6), nullable=False, default=Decimal("0"))
    realised_pnl  = db.Column(db.Numeric(18, 6), nullable=False, default=Decimal("0"))
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="positions")

    def __repr__(self) -> str:
        return f"<Position {self.symbol} qty={self.quantity}>"
