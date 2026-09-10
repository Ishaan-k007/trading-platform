from datetime import datetime
from extensions import db


class RiskCheck(db.Model):
    __tablename__ = "risk_checks"

    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.String(36), db.ForeignKey("orders.id"), nullable=False)
    approved   = db.Column(db.Boolean, nullable=False)
    reason     = db.Column(db.Text, nullable=True)
    risk_score = db.Column(db.Numeric(5, 2), nullable=True)
    latency_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order = db.relationship("Order", back_populates="risk_check")

    def __repr__(self) -> str:
        return f"<RiskCheck order={self.order_id} approved={self.approved}>"
