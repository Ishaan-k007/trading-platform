"""Read-only dashboard adapters and presentation calculations.

No order submission, account mutation, or strategy execution belongs here.
The sample walkthrough is generated locally and never contacts the backend.
"""

from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
import math
from pathlib import Path
import re
import time

import pandas as pd


STATE_COLUMNS = ["timestamp", "symbol", "price", "cash", "equity"]
TRADE_COLUMNS = ["timestamp", "side", "symbol", "quantity", "fill_price"]
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def parse_symbols(value: str) -> tuple[str, ...]:
    symbols = dict.fromkeys(s.strip().upper() for s in value.split(","))
    return (
        tuple(s for s in symbols if re.fullmatch(r"[A-Z0-9]{1,20}USDT", s))[:5]
        or DEFAULT_SYMBOLS
    )


def age_seconds(timestamp, now=None):
    try:
        value = pd.to_datetime(timestamp, utc=True, errors="coerce")
        if pd.isna(value):
            return None
        current = pd.Timestamp(now or datetime.now(timezone.utc))
        seconds = (current - value).total_seconds()
        return seconds if seconds >= -1 else None
    except (ValueError, TypeError, OverflowError):
        return None


def age_label(seconds):
    if seconds is None:
        return "Unknown"
    seconds = max(0, seconds)
    if seconds < 60:
        return f"{seconds:.0f}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h ago"
    return f"{seconds / 86400:.1f}d ago"


def read_log(path: Path, kind: str) -> tuple[pd.DataFrame, list[str]]:
    """Read a snapshot, ignoring an in-progress final line but reporting bad rows."""
    columns = STATE_COLUMNS if kind == "state" else TRADE_COLUMNS
    empty = pd.DataFrame(columns=columns)
    if not path.exists():
        return empty, []
    try:
        payload = path.read_bytes()
        end = payload.rfind(b"\n")
        if end < 0:
            return empty, []
        frame = pd.read_csv(BytesIO(payload[: end + 1]))
        missing = set(columns) - set(frame.columns)
        if missing:
            return empty, [
                f"{path.name}: missing columns ({', '.join(sorted(missing))})."
            ]
        frame["timestamp"] = pd.to_datetime(
            frame["timestamp"], utc=True, errors="coerce"
        )
        numeric = (
            ["price", "cash", "equity"]
            if kind == "state"
            else ["quantity", "fill_price"]
        )
        valid = frame["timestamp"].notna() & frame["symbol"].notna()
        for col in numeric:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
            valid &= frame[col].map(lambda x: pd.notna(x) and math.isfinite(x))
        valid &= (
            frame["price"].gt(0)
            if kind == "state"
            else frame["quantity"].gt(0) & frame["fill_price"].gt(0)
        )
        if kind == "trades":
            frame["side"] = frame["side"].astype(str).str.upper()
            valid &= frame["side"].isin(["BUY", "SELL"])
        invalid_count = int((~valid).sum())
        frame = frame.loc[valid].copy()
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
        frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
        warnings = (
            [f"{path.name}: {invalid_count} invalid row(s) omitted from the display."]
            if invalid_count
            else []
        )
        return frame, warnings
    except (
        OSError,
        ValueError,
        UnicodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
    ):
        return empty, [
            f"{path.name} could not be read. Waiting for a complete, valid CSV snapshot."
        ]


def summarize_trades(trades: pd.DataFrame) -> dict:
    """FIFO matching per symbol; explicitly detect an incomplete position history."""
    lots = defaultdict(deque)
    exits, wins, realized, unmatched = 0, 0, 0.0, False
    for row in trades.sort_values("timestamp", kind="stable").itertuples():
        qty, price = float(row.quantity), float(row.fill_price)
        if row.side == "BUY":
            lots[row.symbol].append([qty, price])
            continue
        pnl = 0.0
        while qty > 1e-9 and lots[row.symbol]:
            lot = lots[row.symbol][0]
            matched = min(qty, lot[0])
            pnl += matched * (price - lot[1])
            qty -= matched
            lot[0] -= matched
            if lot[0] < 1e-9:
                lots[row.symbol].popleft()
        if qty > 1e-9:
            unmatched = True
        else:
            exits += 1
            wins += int(pnl > 0)
            realized += pnl
    positions = {}
    for symbol, entries in lots.items():
        quantity = sum(q for q, _ in entries)
        if quantity > 1e-9:
            positions[symbol] = {
                "quantity": quantity,
                "average_price": sum(q * p for q, p in entries) / quantity,
            }
    return {
        "fills": len(trades),
        "exits": exits,
        "win_rate": wins / exits * 100 if exits and not unmatched else None,
        "realized": realized if not unmatched else None,
        "positions": positions,
        "incomplete": unmatched,
    }


def sample_session() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Illustrative zero-fee trades, not recorded executions or investment results."""
    start = pd.Timestamp("2026-01-01T12:00:00Z")
    anchors = [
        100000,
        99700,
        99000,
        99200,
        100200,
        100800,
        100100,
        99200,
        99500,
        100600,
        101000,
        100800,
    ]
    prices = []
    for a, b in zip(anchors, anchors[1:]):
        prices.extend(a + (b - a) * step / 6 for step in range(6))
    prices.append(anchors[-1])
    fills = {12: "BUY", 24: "SELL", 42: "BUY", 54: "SELL"}
    cash, holding = 10000.0, 0.0
    states, trades, markets = [], [], []
    bases = dict(zip(DEFAULT_SYMBOLS, [100000, 3200, 150, 650, 2.4]))
    for i, mid in enumerate(prices):
        timestamp = start + pd.Timedelta(seconds=2 * i)
        if i in fills:
            side = fills[i]
            fill = mid + 2 if side == "BUY" else mid - 2
            quantity = 0.025
            cash += (-1 if side == "BUY" else 1) * quantity * fill
            holding += quantity if side == "BUY" else -quantity
            trades.append(
                dict(
                    timestamp=timestamp,
                    symbol="BTCUSDT",
                    side=side,
                    quantity=quantity,
                    fill_price=fill,
                    order_id=f"SAMPLE-{len(trades) + 1:03}",
                    currency="USDT",
                )
            )
        states.append(
            dict(
                timestamp=timestamp,
                symbol="BTCUSDT",
                price=mid,
                cash=round(cash, 6),
                equity=round(cash + holding * mid, 6),
                currency="USDT",
            )
        )
        for j, (symbol, base) in enumerate(bases.items()):
            price = (
                mid
                if j == 0
                else base
                * (1 + 0.55 * (mid / 100000 - 1) + 0.0008 * math.sin(i / 4 + j))
            )
            spread = 4 if j == 0 else price * 0.00012
            markets.append(
                dict(
                    timestamp=timestamp,
                    symbol=symbol,
                    price=price,
                    best_bid=price - spread / 2,
                    best_ask=price + spread / 2,
                )
            )
    return pd.DataFrame(states), pd.DataFrame(trades), pd.DataFrame(markets)


class MarketReader:
    """Independent read-only adapter; does not depend on OrderService internals."""

    def __init__(self, host: str, port: int):
        import grpc
        from services import trading_pb2_grpc

        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = trading_pb2_grpc.TradingServiceStub(self.channel)

    def quotes(self, symbols: tuple[str, ...]) -> list[dict]:
        import grpc
        from services import trading_pb2

        def fetch(symbol):
            started = time.perf_counter()
            try:
                response = self.stub.GetPrice(
                    trading_pb2.GetPriceRequest(symbol=symbol), timeout=0.7
                )
                bid, ask, price = response.best_bid, response.best_ask, response.price
                valid = (
                    all(math.isfinite(x) and x > 0 for x in (bid, ask, price))
                    and ask >= bid
                )
                return {
                    "symbol": symbol,
                    "price": price,
                    "best_bid": bid,
                    "best_ask": ask,
                    "updated_at": response.updated_at,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "sample_id": started,
                    "reachable": True,
                    "error": None if valid else "Invalid quote",
                }
            except grpc.RpcError as exc:
                reachable = exc.code() not in (
                    grpc.StatusCode.UNAVAILABLE,
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                )
                return {
                    "symbol": symbol,
                    "reachable": reachable,
                    "error": "No quote" if reachable else "Unavailable",
                }

        with ThreadPoolExecutor(max_workers=len(symbols)) as pool:
            return list(pool.map(fetch, symbols))


def database_status(engine, username: str) -> dict:
    """One read transaction, scoped to the configured shared strategy account."""
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL statement_timeout = '1000ms'"))
            connection.execute(text("SELECT 1"))
            row = (
                connection.execute(
                    text(
                        """
                SELECT a.currency, COUNT(o.id) AS fills, MAX(o.created_at) AS last_fill
                FROM users u JOIN accounts a ON a.user_id = u.id
                LEFT JOIN orders o ON o.user_id = u.id AND o.status = 'FILLED'
                WHERE u.username = :username GROUP BY a.id, a.currency
            """
                    ),
                    {"username": username},
                )
                .mappings()
                .first()
            )
            if row is None:
                return {
                    "online": True,
                    "account_found": False,
                    "fills": 0,
                    "currency": None,
                    "last_fill": None,
                }
            return {"online": True, "account_found": True, **dict(row)}
    except Exception:
        # Connection errors may contain credentials; never put raw exceptions in the UI.
        return {
            "online": False,
            "account_found": False,
            "fills": None,
            "currency": None,
            "last_fill": None,
        }
