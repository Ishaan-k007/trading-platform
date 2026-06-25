from decimal import Decimal


class TradingError(Exception):
    """Base exception for all domain errors."""
    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"


class InsufficientFundsError(TradingError):
    http_status = 402
    error_code = "INSUFFICIENT_FUNDS"

    def __init__(self, balance: Decimal, required: Decimal) -> None:
        self.balance = balance
        self.required = required
        super().__init__(
            f"Cash balance of {balance} is insufficient. Order requires {required}."
        )


class InsufficientPositionError(TradingError):
    http_status = 400
    error_code = "INSUFFICIENT_POSITION"

    def __init__(self, symbol: str, held: Decimal, required: Decimal) -> None:
        super().__init__(
            f"You hold {held} {symbol} but tried to sell {required}."
        )


class SymbolNotAllowedError(TradingError):
    http_status = 400
    error_code = "SYMBOL_NOT_ALLOWED"

    def __init__(self, symbol: str) -> None:
        super().__init__(f"{symbol} is not a supported symbol.")


class OrderNotFoundError(TradingError):
    http_status = 404
    error_code = "ORDER_NOT_FOUND"


class OrderNotCancellableError(TradingError):
    http_status = 409
    error_code = "ORDER_NOT_CANCELLABLE"

    def __init__(self, status: str) -> None:
        super().__init__(f"Order cannot be cancelled — current status is {status}.")


class DuplicateRequestError(TradingError):
    http_status = 409
    error_code = "DUPLICATE_REQUEST"


class InvalidCredentialsError(TradingError):
    http_status = 401
    error_code = "INVALID_CREDENTIALS"
