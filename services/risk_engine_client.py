import time
from urllib import request

import grpc
from services import trading_pb2, trading_pb2_grpc
from core.exceptions import RiskEngineUnavailableError, SymbolNotFoundError
from core.metrics import EXECUTE_ORDER_LATENCY




class RiskEngineClient:
    """gRPC client wrapping the C++ TradingService.

    Translates gRPC calls into plain Python dicts and raises domain exceptions so callers never need to handle gRPC types directly.
    """
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.channel = grpc.insecure_channel(f"{self.host}:{self.port}")
        self.stub = trading_pb2_grpc.TradingServiceStub(self.channel)

    
        
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
        
    def execute_order(self, user_id: int, client_order_id: str, side: str, symbol: str,
                      quantity: float, order_type: str, limit_price: float | None) -> dict:
        """Execute an order atomically in the C++ engine.

        One round-trip: the engine validates, prices, checks funds/position,
        writes the WAL entry, and mutates its in-memory state under a single
        held per-user lock. Python computes no balances.

        Returns a dict with the typed result code and, depending on it, the
        fill details or the real shortfall amounts.

        Raises:
            RiskEngineUnavailableError: if the engine is unreachable or times out.
        """
        request = trading_pb2.ExecuteOrderRequest(
            client_order_id=client_order_id,
            user_id=user_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price or 0.0,
        )
        start = time.perf_counter()
        try:
            r = self.stub.ExecuteOrder(request, timeout=2)
        except grpc.RpcError:
            raise RiskEngineUnavailableError()
        finally:
            EXECUTE_ORDER_LATENCY.observe(time.perf_counter() - start)

        return {
            "result": r.result,
            "result_name": trading_pb2.OrderResultCode.Name(r.result),
            "order_id": r.order_id,
            "event_id": r.event_id,
            "client_order_id": r.client_order_id,
            "fill_price": r.fill_price,
            "market_price": r.market_price,
            "required_cash": r.required_cash,
            "available_cash": r.available_cash,
            "required_quantity": r.required_quantity,
            "available_quantity": r.available_quantity,
            "new_cash": r.new_cash,
            "new_quantity": r.new_quantity,
            "account_sequence": r.account_sequence,
            "message": r.message,
        }
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
