from datetime import datetime
from decimal import Decimal
from extensions import db
from core.money import ACCOUNT_CURRENCY, CURRENCY_CODE_LENGTH, DECIMAL_PRECISION, DECIMAL_SCALE


class Account(db.Model):
    __tablename__ = "accounts"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cash_balance = db.Column(db.Numeric(DECIMAL_PRECISION, DECIMAL_SCALE),
                             nullable=False, default=Decimal("0"))
    currency     = db.Column(db.String(CURRENCY_CODE_LENGTH), nullable=False,
                             default=ACCOUNT_CURRENCY)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    user           = db.relationship("User", back_populates="account")
    ledger_entries = db.relationship("LedgerEntry", back_populates="account")

    def __repr__(self) -> str:
        return f"<Account user={self.user_id} balance={self.cash_balance}>"
