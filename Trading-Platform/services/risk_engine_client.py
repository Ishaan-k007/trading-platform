from urllib import request

import grpc
from services import trading_pb2, trading_pb2_grpc
from core.exceptions import RiskEngineUnavailableError, SymbolNotFoundError



class RiskEngineClient:
    """gRPC client wrapping the C++ TradingService.

    Translates gRPC calls into plain Python dicts and raises domain exceptions so callers never need to handle gRPC types directly.
    """
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.channel = grpc.insecure_channel(f"{self.host}:{self.port}")
        self.stub = trading_pb2_grpc.TradingServiceStub(self.channel)

    def check_order(self, user_id: int, order_id: str, side: str, symbol: str, quantity: float, order_type: str, limit_price: float) -> dict:
        """Submit an order to the risk engine for approval.

        Args:
            user_id: ID of the user placing the order.
            order_id: Unique order identifier for idempotency tracking.
            side: 'BUY' or 'SELL'.
            symbol: Stock ticker e.g. 'AAPL'.
            quantity: Number of shares.
            order_type: 'MARKET' or 'LIMIT'.
            limit_price: Required for LIMIT orders, ignored for MARKET.

        Returns:
            dict with keys: approved (bool), fill_price (float), reason (str).

        Raises:
            RiskEngineUnavailableError: If the C++ engine is unreachable or times out.
        """
        request = trading_pb2.CheckOrderRequest(user_id=user_id, order_id = order_id, symbol=symbol,side=side,order_type=order_type,quantity=quantity, limit_price=limit_price)
        try:
            response = self.stub.CheckOrder(request, timeout = 2) 
            return {"approved": response.approved, "fill_price": response.fill_price, "reason": response.reason}
        
        
        except grpc.RpcError:
            raise RiskEngineUnavailableError()
        
    
    def update_state(self, user_id: int, symbol: str, new_cash: float, new_quantity: float, 
                 new_avg_price: float, order_id: str, side: str, fill_price: float, 
                 quantity: float, order_type: str) -> None:
        """Sync the C++ engine's in-memory state after a confirmed fill.

        Must be called only after the PostgreSQL transaction has committed,
        so the in-memory state never gets ahead of the DB.
        
        Args:
            user_id: ID of the user whose state to update.
            symbol: Stock ticker of the filled position e.g. 'AAPL'.
            new_cash: Updated cash balance after the trade.
            new_quantity: Updated share quantity after the trade.
            new_avg_price: Updated average purchase price after the trade.


        Raises:
            RiskEngineUnavailableError: If the C++ engine is unreachable.
        """
        
        request = trading_pb2.UpdateStateRequest(
        user_id=user_id,
        symbol=symbol,
        new_cash_balance=new_cash,
        new_quantity=new_quantity,
        new_average_price=new_avg_price,
        order_id=order_id,
        side=side,
        fill_price=fill_price,
        quantity=quantity,
        order_type=order_type,
    )
    try:
        self.stub.UpdateState(request, timeout=2)
    except grpc.RpcError:
        raise RiskEngineUnavailableError()
        
        
    def load_user(self, user_id: int, cash_balance: float, positions: list[dict]) -> None:
        """Load a user's state into the C++ engine on login or first order.

        Args:
            user_id: ID of the user to load.
            cash_balance: Current cash balance from PostgreSQL.
            positions: List of dicts, each with keys: symbol, quantity, average_price.

        Raises:
            RiskEngineUnavailableError: If the C++ engine is unreachable.
        """
        
        position_entries = []
        for position in positions:
            position_entries.append(trading_pb2.PositionEntry(symbol = position["symbol"], quantity = position["quantity"], average_price = position["average_price"] ))
        
        request = trading_pb2.LoadUserRequest(user_id = user_id, cash_balance = cash_balance, positions = position_entries) 

        try:
            response = self.stub.LoadUser(request, timeout = 2)
            return
        except grpc.RpcError:
            raise RiskEngineUnavailableError()
        

    def get_price(self, symbol: str) -> dict:
        """Fetch the current market price for a given stock symbol.

        Args:
            symbol: Stock ticker e.g. 'AAPL'.

        Returns:
            dict with keys: symbol (str), price (float), updated_at (str).

        Raises:
            RiskEngineUnavailableError: If the C++ engine is unreachable.
        """
        request = trading_pb2.GetPriceRequest(symbol = symbol)
        try:
            response = self.stub.GetPrice(request, timeout = 2)
            return {"symbol": response.symbol, "price": response.price, "updated_at": response.updated_at}
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise SymbolNotFoundError(symbol)
            raise RiskEngineUnavailableError()

                
    def get_all_prices(self) -> dict[str, float]:
        """Fetch current prices for all tracked symbols from the C++ engine.

        Returns:
            dict mapping symbol (str) to price (float) e.g. {'AAPL': 182.5}.

        Raises:
            RiskEngineUnavailableError: If the C++ engine is unreachable.
        """
        request = trading_pb2.GetAllPricesRequest()
        try:
            response = self.stub.GetAllPrices(request, timeout = 2)
            return dict(response.prices)

        except grpc.RpcError:
            raise RiskEngineUnavailableError()
    
    
    def has_user(self, user_id: int) -> bool:
        """Check if user state is already loaded in C++ engine."""
        request = trading_pb2.HasUserRequest(user_id=user_id)
        try:
            response = self.stub.HasUser(request, timeout=2)
            return response.loaded
        except grpc.RpcError:
            raise RiskEngineUnavailableError()
