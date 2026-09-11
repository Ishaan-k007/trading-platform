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

        Must be a *decision*, not a commitment: an intent returned here has
        not been placed, let alone filled, and may be rejected. Implementations
        should not record "I am now holding X" from this method — wait for
        on_fill(). Deciding here and committing there is what stops a rejected
        order from leaving the strategy's view of its own position wrong.

        Args:
            symbol: The ticker this update is for.
            price: Latest price for that ticker.

        Returns:
            Zero or more OrderIntents to submit. Most calls should return
            an empty list — only return intents when the strategy actually
            wants to trade.
        """
        raise NotImplementedError

    def on_fill(self, symbol: str, side: OrderSide, fill_price: float) -> None:
        """Called after an intent from on_price() actually filled.

        This is where position state belongs. `fill_price` is the price the
        engine executed at, which is not the price on_price() saw — that was a
        mid-price from a separate lookup, this is the real bid or ask.

        Args:
            symbol: The ticker that traded.
            side: Which way it went.
            fill_price: The executed price.
        """

    def on_reject(self, symbol: str, side: OrderSide, price: float,
                  reason: str) -> None:
        """Called when an intent from on_price() was refused.

        Nothing happened: no cash moved and no position changed. A strategy
        may want to react anyway — for example by re-anchoring, so it does not
        resubmit the same rejected order on every subsequent tick.

        Args:
            symbol: The ticker that was refused.
            side: Which way the refused order went.
            price: The price on_price() acted on.
            reason: Human-readable rejection reason.
        """
