from decimal import Decimal

from models.order import Order
from models.account import Account
from models.position import Position
from enums import OrderStatus
from core.exceptions import (
    InsufficientFundsError,
    InsufficientPositionError,
    SymbolNotFoundError,
    LimitNotMetError,
    InvalidOrderError,
    DuplicateRequestError,
)
from services.risk_engine_client import RiskEngineClient
from services import trading_pb2


class OrderService:
    """Places orders via the C++ engine's atomic ExecuteOrder RPC."""

    def __init__(self, risk_engine: RiskEngineClient):
        self.risk_engine = risk_engine

    def place_order(self, user_id: int, order_id: str, side: str, symbol: str,
                    quantity: float, order_type: str, limit_price: float | None) -> Order:
        """Execute an order and return the resulting FILLED Order.

        `order_id` is the *client's* id — the idempotency key. It goes to the
        engine unchanged; a retry with the same value replays the original
        outcome instead of executing twice. The engine mints its own canonical
        id, which becomes Order.id.

        Raises: SymbolNotFoundError, LimitNotMetError, InsufficientFundsError,
        InsufficientPositionError, InvalidOrderError, DuplicateRequestError,
        RiskEngineUnavailableError.
        """
        # Ensure the engine has this user's cash/positions in memory.
        if not self.risk_engine.has_user(user_id):
            account = Account.query.filter_by(user_id=user_id).first()
            positions = Position.query.filter_by(user_id=user_id).all()
            self.risk_engine.load_user(
                user_id=user_id,
                cash_balance=float(account.cash_balance),
                positions=[
                    {"symbol": p.symbol, "quantity": float(p.quantity),
                     "average_price": float(p.average_price)}
                    for p in positions
                ],
            )

        result = self.risk_engine.execute_order(
            user_id=user_id,
            client_order_id=order_id,
            side=side,
            symbol=symbol,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        code = result["result"]

        if code == trading_pb2.FILLED:
            return Order(
                id=result["order_id"],
                user_id=user_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                limit_price=limit_price,
                filled_price=Decimal(str(result["fill_price"])),
                status=OrderStatus.FILLED,
                idempotency_key=order_id,
            )

        if code == trading_pb2.UNKNOWN_SYMBOL:
            raise SymbolNotFoundError(symbol)
        if code == trading_pb2.LIMIT_NOT_MET:
            raise LimitNotMetError(side, limit_price, result["market_price"])
        if code == trading_pb2.INSUFFICIENT_FUNDS:
            raise InsufficientFundsError(
                balance=result["available_cash"], required=result["required_cash"])
        if code == trading_pb2.INSUFFICIENT_POSITION:
            raise InsufficientPositionError(
                symbol=symbol,
                held=result["available_quantity"],
                required=result["required_quantity"])
        if code == trading_pb2.IDEMPOTENCY_CONFLICT:
            raise DuplicateRequestError(
                f"client_order_id {order_id} was already used for a different order.")

        raise InvalidOrderError(result["message"] or "Order rejected by the risk engine.")
