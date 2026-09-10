import uuid
from datetime import datetime
from extensions import db
from enums import OrderStatus, OrderSide, OrderType


class Order(db.Model):
    __tablename__ = "orders"

    id               = db.Column(db.String(36), primary_key=True,
                                 default=lambda: str(uuid.uuid4()))
    user_id          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    symbol           = db.Column(db.String(10), nullable=False)
    side             = db.Column(db.String(4), nullable=False)
    order_type       = db.Column(db.String(6), nullable=False, default=OrderType.MARKET)
    quantity         = db.Column(db.Numeric(18, 6), nullable=False)
    limit_price      = db.Column(db.Numeric(18, 6), nullable=True)
    requested_price  = db.Column(db.Numeric(18, 6), nullable=True)
    filled_price     = db.Column(db.Numeric(18, 6), nullable=True)
    status           = db.Column(db.String(15), nullable=False,
                                 default=OrderStatus.PENDING)
    rejection_reason = db.Column(db.Text, nullable=True)
    idempotency_key  = db.Column(db.String(255), unique=True, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)

    user       = db.relationship("User", back_populates="orders")
    risk_check = db.relationship("RiskCheck", back_populates="order", uselist=False)
    ledger_entries = db.relationship("LedgerEntry", back_populates="order")

    def __repr__(self) -> str:
        return f"<Order {self.side} {self.quantity} {self.symbol} [{self.status}]>"
