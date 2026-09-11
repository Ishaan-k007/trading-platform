"""ThresholdStrategy decides in on_price() and commits in on_fill().

The bug these guard against: on_price() used to set `holding[symbol]` and
re-anchor the reference price before returning the intent - before the order
had even been placed. A rejected order left the strategy believing it held a
position it did not, and because it only ever sells what it thinks it holds,
that symbol went silent until the runner was restarted.
"""
from enums import OrderSide
from strategies.threshold_strategy import ThresholdStrategy


def make_strategy(**overrides):
    kwargs = dict(symbols=["BTCUSDT"], drop_pct=0.01, rise_pct=0.01,
                  trade_quantity=1.0)
    kwargs.update(overrides)
    return ThresholdStrategy(**kwargs)


def seed(strategy, price=100.0, symbol="BTCUSDT"):
    """First tick just records the reference and trades nothing."""
    assert strategy.on_price(symbol, price) == []
    return strategy


def test_first_tick_only_seeds_the_reference():
    strategy = make_strategy()
    assert strategy.on_price("BTCUSDT", 100.0) == []
    assert strategy.reference_price["BTCUSDT"] == 100.0
    assert strategy.holding["BTCUSDT"] is False


def test_a_drop_produces_a_buy_intent():
    strategy = seed(make_strategy())
    intents = strategy.on_price("BTCUSDT", 98.0)      # -2%, threshold is -1%
    assert len(intents) == 1
    assert intents[0].side == OrderSide.BUY


def test_on_price_does_not_claim_the_position():
    """The decisive assertion: deciding to buy is not the same as holding."""
    strategy = seed(make_strategy())
    strategy.on_price("BTCUSDT", 98.0)
    assert strategy.holding["BTCUSDT"] is False
    assert strategy.reference_price["BTCUSDT"] == 100.0   # not re-anchored yet


def test_a_fill_commits_the_position_and_anchors_to_the_fill_price():
    strategy = seed(make_strategy())
    strategy.on_price("BTCUSDT", 98.0)
    strategy.on_fill("BTCUSDT", OrderSide.BUY, 97.5)      # engine filled lower
    assert strategy.holding["BTCUSDT"] is True
    assert strategy.reference_price["BTCUSDT"] == 97.5    # the real fill, not 98.0


def test_a_rejected_buy_leaves_the_strategy_flat():
    """The regression. Previously `holding` was already True here, so the
    strategy would wait to sell something it never bought."""
    strategy = seed(make_strategy())
    strategy.on_price("BTCUSDT", 98.0)
    strategy.on_reject("BTCUSDT", OrderSide.BUY, 98.0, "insufficient funds")

    assert strategy.holding["BTCUSDT"] is False
    # and it can still buy again once the price moves down from the new anchor
    assert strategy.on_price("BTCUSDT", 96.0)[0].side == OrderSide.BUY


def test_a_rejection_stops_it_resubmitting_on_every_tick():
    strategy = seed(make_strategy())
    strategy.on_price("BTCUSDT", 98.0)
    strategy.on_reject("BTCUSDT", OrderSide.BUY, 98.0, "insufficient funds")
    # Same price again: the threshold is measured from 98.0 now, not 100.0.
    assert strategy.on_price("BTCUSDT", 98.0) == []


def test_a_full_round_trip():
    strategy = seed(make_strategy())

    buy = strategy.on_price("BTCUSDT", 98.0)[0]
    assert buy.side == OrderSide.BUY
    strategy.on_fill("BTCUSDT", OrderSide.BUY, 98.0)

    assert strategy.on_price("BTCUSDT", 98.5) == []       # +0.5%, not enough
    sell = strategy.on_price("BTCUSDT", 99.5)[0]          # +1.5%, over threshold
    assert sell.side == OrderSide.SELL

    strategy.on_fill("BTCUSDT", OrderSide.SELL, 99.5)
    assert strategy.holding["BTCUSDT"] is False
    assert strategy.reference_price["BTCUSDT"] == 99.5


def test_a_rejected_sell_keeps_the_position():
    strategy = seed(make_strategy())
    strategy.on_price("BTCUSDT", 98.0)
    strategy.on_fill("BTCUSDT", OrderSide.BUY, 98.0)

    strategy.on_price("BTCUSDT", 99.5)
    strategy.on_reject("BTCUSDT", OrderSide.SELL, 99.5, "insufficient position")

    assert strategy.holding["BTCUSDT"] is True    # still holding, nothing sold


def test_symbols_are_tracked_independently():
    strategy = make_strategy(symbols=["BTCUSDT", "ETHUSDT"])
    seed(strategy, 100.0, "BTCUSDT")
    seed(strategy, 200.0, "ETHUSDT")

    strategy.on_price("BTCUSDT", 98.0)
    strategy.on_fill("BTCUSDT", OrderSide.BUY, 98.0)

    assert strategy.holding["BTCUSDT"] is True
    assert strategy.holding["ETHUSDT"] is False
    assert strategy.reference_price["ETHUSDT"] == 200.0
