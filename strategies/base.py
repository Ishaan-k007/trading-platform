from abc import ABC, abstractmethod
from dataclasses import dataclass

from enums import OrderSide, OrderType


@dataclass
class OrderIntent:
    """A strategy's request to trade.

    This is the only thing a Strategy is allowed to hand back to its caller.
    It deliberately mirrors the shape order_service.place_order() expects,
    but stays a plain dataclass so strategies never import services/ or
    models/ directly.
    """
    side: OrderSide
    symbol: str
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None


class Strategy(ABC):
    """Base class for all trading strategies.

    A Strategy only ever sees prices in and OrderIntents out — it has no
    knowledge of the risk engine, the database, or how (or whether) its
    orders actually get filled. Whoever drives the strategy (a live runner
    polling real prices, or eventually a backtester replaying historical
    ones) owns everything past on_price().
    """

    def __init__(self, symbols: list[str]) -> None:
        """Args:
            symbols: Tickers this strategy wants price updates for.
        """
        self.symbols = symbols

    @abstractmethod
    def on_price(self, symbol: str, price: float) -> list[OrderIntent]:
        """Called once per price update for each symbol in self.symbols.

        Args:
            symbol: The ticker this update is for.
            price: Latest price for that ticker.

        Returns:
            Zero or more OrderIntents to submit. Most calls should return
            an empty list — only return intents when the strategy actually
            wants to trade.
        """
        raise NotImplementedError
