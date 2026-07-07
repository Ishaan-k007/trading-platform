from decimal import Decimal
from models.order import Order
from models.account import Account
from models.position import Position
from enums import OrderStatus
from core.exceptions import InsufficientFundsError, InsufficientPositionError
from services.risk_engine_client import RiskEngineClient
import uuid

class OrderService:
    """Handles order placement, risk validation, and atomic trade execution."""
    def __init__(self, risk_engine: RiskEngineClient):
        """Initialise the OrderService with a gRPC risk engine client.

        Args:
            risk_engine: Connected RiskEngineClient instance injected from app factory.
        """

        self.risk_engine = risk_engine
    
    def place_order(self, user_id: int, order_id: str, side: str, symbol: str, quantity: float, order_type: str, limit_price: float) -> Order:
        """Place an order and return the result.

        Args:
            user_id: ID of the user placing the order.
            order_id: Unique order identifier for idempotency tracking.
            side: 'BUY' or 'SELL'.
            symbol: Stock ticker e.g. 'AAPL'.
            quantity: Number of shares.
            order_type: 'MARKET' or 'LIMIT'.
            limit_price: Required for LIMIT orders, ignored for MARKET.
        Returns:
            The filled Order object with status FILLED and fill_price set.

        Raises:
            SymbolNotFoundError: If the symbol is not tracked by the risk engine.
            InsufficientFundsError: If the user has insufficient cash for a BUY.
            InsufficientPositionError: If the user has insufficient shares for a SELL.
            RiskEngineUnavailableError: If the C++ engine is unreachable.
        """
                
        self.risk_engine.get_price(symbol)

        if not self.risk_engine.has_user(user_id):
            account = Account.query.filter_by(user_id=user_id).first()
            positions = Position.query.filter_by(user_id=user_id).all()
            self.risk_engine.load_user(
                user_id=user_id,
                cash_balance=float(account.cash_balance),
                positions=[{"symbol": p.symbol, "quantity": float(p.quantity), "average_price": float(p.average_price)} for p in positions]
            )

        
        
        result = self.risk_engine.check_order(user_id, order_id, side, symbol, quantity, order_type, limit_price)
        
        if not result["approved"]:
            if side == "BUY":
                account = Account.query.filter_by(user_id=user_id).first()
                required = Decimal(str(quantity)) * Decimal(str(result.get("fill_price", limit_price)))
                raise InsufficientFundsError(
                    balance=account.cash_balance,
                    required=required,
                )
            else:
                position = Position.query.filter_by(user_id=user_id, symbol=symbol).first()
                held = position.quantity if position else Decimal("0")
                raise InsufficientPositionError(
                    symbol=symbol,
                    held=held,
                    required=Decimal(str(quantity)),
                )


        order = Order(id=str(uuid.uuid4()), user_id=user_id, symbol=symbol, side=side, order_type=order_type, quantity=quantity, limit_price=limit_price, status=OrderStatus.PENDING)
        self._execute_fill(user_id, order, result["fill_price"])

        
        return order
    
    def _execute_fill(self, user_id: int, order: Order, fill_price:float) -> None:
        """Compute new state, sync C++ engine, and write WAL entry after a risk-approved order.

        Args:
            user_id: ID of the user whose state to update.
            order: The filled Order object.
            fill_price: Approved fill price returned by the risk engine.
        """

                
        
        
        order.status = OrderStatus.FILLED
        order.filled_price = Decimal(str(fill_price))
        side = order.side
        quantity = float(order.quantity)
        symbol = order.symbol
        

        account = Account.query.filter_by(user_id=user_id).first()
        position = Position.query.filter_by(user_id=user_id, symbol=symbol).first()
        old_cash = float(account.cash_balance)  
        old_quantity = float(position.quantity) if position else 0.0
        old_avg_price = float(position.average_price) if position else 0.0

        
        if side == "BUY":
            new_cash = old_cash - quantity * fill_price
            new_quantity = old_quantity + quantity
            new_avg_price = (old_quantity * old_avg_price + quantity * fill_price) / new_quantity
        else:
            new_cash = old_cash + quantity * fill_price
            new_quantity = old_quantity - quantity
            new_avg_price = old_avg_price
        self.risk_engine.update_state(
            user_id=user_id,
            symbol=symbol,
            new_cash=new_cash,
            new_quantity=new_quantity,
            new_avg_price=new_avg_price,
            order_id=order.id,
            side=side,
            fill_price=fill_price,
            quantity=quantity,
            order_type=order.order_type,
        )
                

        
        
        



            
            
        
            
     
              