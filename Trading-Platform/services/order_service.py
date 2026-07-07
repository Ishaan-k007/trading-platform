from decimal import Decimal
from models.order import Order
from models.account import Account
from models.position import Position
from models.ledger_entry import LedgerEntry
from enums import OrderStatus, EntryType
from extensions import db
from core.exceptions import InsufficientFundsError, InsufficientPositionError
from services.risk_engine_client import RiskEngineClient

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
                
        # Ensure the symbol is known to the risk engine before proceeding
        self.risk_engine.get_price(symbol)
        # Load fresh user state from DB into C++ before every risk check
        account = Account.query.filter_by(user_id=user_id).first()
        positions = Position.query.filter_by(user_id=user_id).all()

        self.risk_engine.load_user(user_id=user_id,cash_balance=float(account.cash_balance),positions=[{"symbol": p.symbol,"quantity": float(p.quantity),"average_price": float(p.average_price)} for p in positions])
        
        result = self.risk_engine.check_order(user_id, order_id, side, symbol, quantity, order_type, limit_price)
        
        if not result["approved"]:
            if side == "BUY":
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


        order = Order(user_id = user_id, symbol = symbol, side = side, order_type = order_type, quantity = quantity, limit_price = limit_price, status = OrderStatus.PENDING)
        db.session.add(order)
        db.session.flush() # gets order.id without committing
        self._execute_fill(user_id, order, result["fill_price"])

        
        return order
    
    def _execute_fill(self, user_id: int, order: Order, fill_price:float) -> None:
        """Execute the atomic DB fill after a risk-approved order.

        Writes order status, account cash, position, and ledger entry in one
        transaction. Rolls back C++ in-memory state if the DB commit fails.
        Must only be called after order has been flushed to obtain an order.id.

        Args:
            user_id: ID of the user whose state to update.
            order: The flushed Order object to fill.
            fill_price: Approved fill price returned by the risk engine.

        Raises:
            Exception: Re-raises any DB commit failure after rolling back C++ state.
        """

        
        
        
        order.status = OrderStatus.FILLED
        order.filled_price = Decimal(str(fill_price))
        side = order.side
        quantity = order.quantity
        symbol = order.symbol
        

        account = Account.query.filter_by(user_id=user_id).with_for_update().first()
        # with_for_update() locks the row and prevents race conditions
        position = Position.query.filter_by(user_id=user_id, symbol=symbol).first()
        old_cash = float(account.cash_balance)  
        old_quantity = float(position.quantity) if position else 0.0
        old_avg_price = float(position.average_price) if position else 0.0

        
        if side == "BUY":
            account.cash_balance -= Decimal(str(fill_price)) * Decimal(str(quantity))
        else:
            account.cash_balance += Decimal(str(fill_price)) * Decimal(str(quantity))

        

        
        
        if position is None:
            position = Position(user_id=user_id, symbol=symbol, quantity=0, average_price=0)
            db.session.add(position)

        if side == "BUY":
            new_qty = position.quantity + Decimal(str(quantity))
            position.average_price = (
                (position.quantity * position.average_price) + (Decimal(str(quantity)) * Decimal(str(fill_price)))
            ) / new_qty
            position.quantity = new_qty
        else:
            position.quantity -= Decimal(str(quantity))
            
        entry_type = EntryType.TRADE_BUY_DEBIT if side == "BUY" else EntryType.TRADE_SELL_CREDIT
        amount = Decimal(str(fill_price)) * Decimal(str(quantity))

        ledger = LedgerEntry(
            user_id=user_id,
            account_id=account.id,
            order_id=order.id,
            entry_type=entry_type,
            amount=amount,
            running_balance=account.cash_balance,
            currency=account.currency,
            description=f"{side} {quantity} {symbol} @ {fill_price}",
        )
        db.session.add(ledger)
        
        

        try:
            db.session.commit()
            self.risk_engine.update_state(
            user_id=user_id,
            symbol=symbol,
            new_cash=float(account.cash_balance),
            new_quantity=float(position.quantity),
            new_avg_price=float(position.average_price),
        )

        
        except Exception:
            db.session.rollback()
            self.risk_engine.update_state(user_id, symbol, old_cash, old_quantity, old_avg_price)
            raise




            
            
        
            
     
              