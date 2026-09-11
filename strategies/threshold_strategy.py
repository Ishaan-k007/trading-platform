from enums import OrderSide, OrderType
from strategies.base import OrderIntent, Strategy


class ThresholdStrategy(Strategy):
    """Buy-the-dip / sell-the-rip.

    Not meant to be profitable — it exists to prove the pipeline (live
    Binance data -> strategy -> risk-checked order -> fill -> accounting)
    works end to end. Behaviour per symbol:

    - No reference price seen yet -> record this price as the reference,
      take no action.
    - Not holding, and price has fallen `drop_pct` below the reference ->
      BUY `trade_quantity`, reset the reference to this (entry) price.
    - Holding, and price has risen `rise_pct` above the reference -> SELL
      `trade_quantity`, reset the reference to this (exit) price.
    - Otherwise -> do nothing.
    """

    def __init__(
        self,
        symbols: list[str],
        drop_pct: float,
        rise_pct: float,
        trade_quantity: float,
    ) -> None:
        """Args:
            symbols: Tickers to trade, e.g. ["BTCUSDT"].
            drop_pct: Fractional drop from the reference price that triggers a BUY (e.g. 0.005 = 0.5%).
            rise_pct: Fractional rise from the reference price that triggers a SELL.
            trade_quantity: Fixed quantity to buy/sell each time, per symbol.
        """
        super().__init__(symbols)
        self.drop_pct = drop_pct
        self.rise_pct = rise_pct
        self.trade_quantity = trade_quantity

        self.reference_price: dict[str, float] = {}
        self.holding: dict[str, bool] = {symbol: False for symbol in symbols}

    def on_price(self, symbol: str, price: float) -> list[OrderIntent]:
        """Decide only. Position state is committed in on_fill().

        This method used to set `holding[symbol]` and re-anchor the reference
        price before returning the intent - i.e. before the order had been
        placed, never mind filled. A rejected order then left the strategy
        believing it held a position it did not, and since it only sells what
        it thinks it holds, that symbol stopped trading until a restart.
        """
        reference = self.reference_price.get(symbol)

        # First tick for this symbol - nothing to compare against yet. Seeding
        # the reference is bookkeeping, not a trading decision, so it is safe
        # to do here.
        if reference is None:
            self.reference_price[symbol] = price
            return []

        if not self.holding[symbol] and price <= reference * (1 - self.drop_pct):
            return [OrderIntent(
                side=OrderSide.BUY,
                symbol=symbol,
                quantity=self.trade_quantity,
                order_type=OrderType.MARKET,
            )]

        if self.holding[symbol] and price >= reference * (1 + self.rise_pct):
            return [OrderIntent(
                side=OrderSide.SELL,
                symbol=symbol,
                quantity=self.trade_quantity,
                order_type=OrderType.MARKET,
            )]

        return []

    def on_fill(self, symbol: str, side: OrderSide, fill_price: float) -> None:
        """Commit the position change, now that it has actually happened.

        The reference anchors to `fill_price` - what the engine really executed
        at - rather than the mid-price on_price() acted on. The next threshold
        is therefore measured from the true entry or exit.
        """
        self.holding[symbol] = (side == OrderSide.BUY)
        self.reference_price[symbol] = fill_price

    def on_reject(self, symbol: str, side: OrderSide, price: float,
                  reason: str) -> None:
        """Nothing traded, so `holding` stays exactly as it was.

        The reference re-anchors to the current price so the strategy waits for
        a fresh move instead of resubmitting the same refused order on every
        tick for as long as the threshold stays breached.
        """
        self.reference_price[symbol] = price
