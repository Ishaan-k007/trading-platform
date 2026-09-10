from datetime import datetime
from extensions import db


class MarketPrice(db.Model):
    __tablename__ = "market_prices"

    symbol     = db.Column(db.String(10), primary_key=True)
    price      = db.Column(db.Numeric(18, 6), nullable=False)
    sector     = db.Column(db.String(50))
    volatility = db.Column(db.Numeric(6, 4), nullable=False, default=0.02)
    drift      = db.Column(db.Numeric(6, 4), nullable=False, default=0.0001)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<MarketPrice {self.symbol}={self.price}>"
