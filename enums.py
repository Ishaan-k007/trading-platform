from enum import Enum


class OrderStatus(str, Enum):
    PENDING       = "PENDING"
    APPROVED      = "APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    OPEN          = "OPEN"
    FILLED        = "FILLED"
    CANCELLED     = "CANCELLED"
    FAILED        = "FAILED"


class OrderSide(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"


class EntryType(str, Enum):
    DEPOSIT           = "DEPOSIT"
    WITHDRAWAL        = "WITHDRAWAL"
    TRADE_BUY_DEBIT   = "TRADE_BUY_DEBIT"
    TRADE_SELL_CREDIT = "TRADE_SELL_CREDIT"
    FEE               = "FEE"
    REFUND            = "REFUND"
