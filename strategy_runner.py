"""Runs one hardcoded strategy against live Binance prices, submitting real
orders through the existing risk-checked pipeline into a dedicated paper
account.

Deliberately outside the Flask request cycle - same pattern as
pipeline/fill_consumer.py: build the app once for its DB/risk-engine
wiring, then hold app_context() for the life of the process.

Writes two CSV logs under logs/ so streamlit_app.py can plot an equity
curve and a price/trade chart without touching Postgres or gRPC directly:
    logs/strategy_state.csv   - one row per poll: price, cash, equity
    logs/strategy_trades.csv  - one row per fill: side, symbol, qty, price

Usage:
    poetry run python strategy_runner.py
"""
import csv
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app import create_app
from core.exceptions import (
    InsufficientFundsError,
    InsufficientPositionError,
    RiskEngineUnavailableError,
    SymbolNotFoundError,
)
from models.account import Account
from models.position import Position
from models.user import User
from services.auth_service import AuthService
from strategies.threshold_strategy import ThresholdStrategy

STRATEGY_USERNAME = os.getenv("STRATEGY_USERNAME", "strategy_bot")
STRATEGY_EMAIL = os.getenv("STRATEGY_EMAIL", "strategy_bot@paper.local")
STRATEGY_PASSWORD = os.getenv("STRATEGY_PASSWORD", "not-a-real-login")

SYMBOLS = os.getenv("STRATEGY_SYMBOLS", "BTCUSDT").split(",")
DROP_PCT = float(os.getenv("STRATEGY_DROP_PCT", "0.005"))
RISE_PCT = float(os.getenv("STRATEGY_RISE_PCT", "0.005"))
TRADE_QUANTITY = float(os.getenv("STRATEGY_TRADE_QUANTITY", "0.01"))
POLL_INTERVAL_SECONDS = float(os.getenv("STRATEGY_POLL_INTERVAL_SECONDS", "2"))

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
STATE_LOG_PATH = os.path.join(LOG_DIR, "strategy_state.csv")
TRADES_LOG_PATH = os.path.join(LOG_DIR, "strategy_trades.csv")


def get_or_create_strategy_user() -> User:
    """Fetch this strategy's dedicated paper account, creating it (with the
    normal starting balance and opening ledger entry) on first run.

    Reuses AuthService so the account is set up exactly like any other user
    - no separate bootstrap logic to keep in sync with the real signup path.
    """
    user = User.query.filter_by(username=STRATEGY_USERNAME).first()
    if user:
        return user
    print(f"[strategy_runner] No account for {STRATEGY_USERNAME} yet, creating one")
    return AuthService().register(
        email=STRATEGY_EMAIL, username=STRATEGY_USERNAME, password=STRATEGY_PASSWORD
    )


def append_csv(path: str, header: list[str], row: list) -> None:
    """Append one row to a CSV, writing the header first if the file is new."""
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(header)
        writer.writerow(row)


def compute_equity(user_id: int, risk_engine) -> tuple[Decimal, Decimal]:
    """Mark open positions to the current market price and return (cash, total_equity).

    Reads straight from Postgres rather than tracking state locally, since
    the WAL/Kafka pipeline is already the source of truth for cash and
    positions - this can lag a fill by a poll cycle or two, which is fine
    for a dashboard refreshing every few seconds.
    """
    account = Account.query.filter_by(user_id=user_id).first()
    positions = Position.query.filter_by(user_id=user_id).all()

    market_value = Decimal("0")
    for position in positions:
        try:
            price = risk_engine.get_price(position.symbol)["price"]
        except (RiskEngineUnavailableError, SymbolNotFoundError):
            continue
        market_value += position.quantity * Decimal(str(price))

    return account.cash_balance, account.cash_balance + market_value


def run() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    app = create_app()

    with app.app_context():
        user = get_or_create_strategy_user()
        strategy = ThresholdStrategy(
            symbols=SYMBOLS,
            drop_pct=DROP_PCT,
            rise_pct=RISE_PCT,
            trade_quantity=TRADE_QUANTITY,
        )

        print(f"[strategy_runner] Trading as user_id={user.id} ({STRATEGY_USERNAME}) on {SYMBOLS}")

        while True:
            for symbol in strategy.symbols:
                try:
                    price = app.risk_engine.get_price(symbol)["price"]
                except SymbolNotFoundError:
                    print(f"[strategy_runner] {symbol} has no price yet (feed still connecting?), skipping")
                    continue
                except RiskEngineUnavailableError:
                    print("[strategy_runner] risk engine unavailable, retrying next cycle")
                    continue

                for intent in strategy.on_price(symbol, price):
                    order_id = str(uuid.uuid4())
                    try:
                        order = app.order_service.place_order(
                            user_id=user.id,
                            order_id=order_id,
                            side=intent.side.value,
                            symbol=intent.symbol,
                            quantity=intent.quantity,
                            order_type=intent.order_type.value,
                            limit_price=intent.limit_price,
                        )
                        # Only now does the strategy learn it holds (or has
                        # released) the position. on_price() deliberately does
                        # not assume its own intent succeeded.
                        strategy.on_fill(intent.symbol, intent.side,
                                         float(order.filled_price))
                        print(f"[strategy_runner] {intent.side.value} {intent.quantity} {intent.symbol} @ {order.filled_price}")
                        append_csv(
                            TRADES_LOG_PATH,
                            ["timestamp", "side", "symbol", "quantity", "fill_price"],
                            [
                                datetime.now(timezone.utc).isoformat(),
                                intent.side.value,
                                intent.symbol,
                                intent.quantity,
                                float(order.filled_price),
                            ],
                        )
                    except (InsufficientFundsError, InsufficientPositionError) as e:
                        # Refused outright: nothing moved, so tell the strategy
                        # rather than letting it keep resubmitting.
                        strategy.on_reject(intent.symbol, intent.side, price, str(e))
                        print(f"[strategy_runner] order rejected: {e}")
                    except RiskEngineUnavailableError:
                        # Genuinely ambiguous - the engine may have committed
                        # the fill before the connection failed. Report neither
                        # outcome and leave the strategy's state untouched; if
                        # the threshold still holds next tick it will simply
                        # decide again.
                        print("[strategy_runner] risk engine unavailable while placing order, skipping")

                cash, equity = compute_equity(user.id, app.risk_engine)
                append_csv(
                    STATE_LOG_PATH,
                    ["timestamp", "symbol", "price", "cash", "equity"],
                    [datetime.now(timezone.utc).isoformat(), symbol, price, float(cash), float(equity)],
                )

            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
