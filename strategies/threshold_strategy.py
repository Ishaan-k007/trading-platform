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
        reference = self.reference_price.get(symbol)

        # First tick for this symbol - nothing to compare against yet.
        if reference is None:
            self.reference_price[symbol] = price
            return []

        if not self.holding[symbol] and price <= reference * (1 - self.drop_pct):
            self.holding[symbol] = True
            self.reference_price[symbol] = price  # anchor to the entry price
            return [OrderIntent(
                side=OrderSide.BUY,
                symbol=symbol,
                quantity=self.trade_quantity,
                order_type=OrderType.MARKET,
            )]

        if self.holding[symbol] and price >= reference * (1 + self.rise_pct):
            self.holding[symbol] = False
            self.reference_price[symbol] = price  # anchor to the exit price
            return [OrderIntent(
                side=OrderSide.SELL,
                symbol=symbol,
                quantity=self.trade_quantity,
                order_type=OrderType.MARKET,
            )]

        return []
