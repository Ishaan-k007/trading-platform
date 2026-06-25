import uuid
from datetime import datetime
from extensions import db


class LedgerEntry(db.Model):
    __tablename__ = "ledger_entries"

    id              = db.Column(db.String(36), primary_key=True,
                                default=lambda: str(uuid.uuid4()))
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_id      = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    order_id        = db.Column(db.String(36), db.ForeignKey("orders.id"), nullable=True)
    entry_type      = db.Column(db.String(20), nullable=False)
    amount          = db.Column(db.Numeric(18, 6), nullable=False)
    running_balance = db.Column(db.Numeric(18, 6), nullable=False)
    currency        = db.Column(db.String(3), nullable=False, default="GBP")
    description     = db.Column(db.Text, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    account = db.relationship("Account", back_populates="ledger_entries")
    order   = db.relationship("Order", back_populates="ledger_entries")

    def __repr__(self) -> str:
        return f"<LedgerEntry {self.entry_type} {self.amount}>"
