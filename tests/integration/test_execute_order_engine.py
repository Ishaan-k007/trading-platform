"""End-to-end tests against a running C++ risk engine on :50051.

The race-condition fix and the idempotency cache are C++ concurrency
behaviours - a mocked client cannot exercise them, so these tests talk to a
real engine. They seed their own synthetic symbol via UpdateOrderBook and use
a random user id per run, so they need no database and leave no state behind
that a later run depends on.

Skipped automatically when the engine isn't running.
"""
import random
import socket
from concurrent.futures import ThreadPoolExecutor

import grpc
import pytest

from services import trading_pb2, trading_pb2_grpc

ENGINE_ADDRESS = "localhost:50051"
SYMBOL = "TESTUSDT"
PRICE = 100.0
STARTING_CASH = 10_000.0


def _engine_up() -> bool:
    try:
        with socket.create_connection(("localhost", 50051), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _engine_up(), reason="risk engine not running on :50051")


@pytest.fixture(scope="module")
def stub():
    channel = grpc.insecure_channel(ENGINE_ADDRESS)
    yield trading_pb2_grpc.TradingServiceStub(channel)
    channel.close()


@pytest.fixture
def account(stub):
    """A fresh user holding STARTING_CASH, plus a synthetic symbol at PRICE.

    LoadUser is a no-op for a user the engine already knows, so each test gets
    a random id to guarantee it starts from a clean balance.
    """
    stub.UpdateOrderBook(trading_pb2.OrderBookUpdateRequest(
        symbol=SYMBOL,
        bids=[trading_pb2.PriceLevel(price=PRICE, quantity=1_000_000.0)],
        asks=[trading_pb2.PriceLevel(price=PRICE, quantity=1_000_000.0)],
        updated_at="test",
    ))
    user_id = random.randint(10_000_000, 99_999_999)
    stub.LoadUser(trading_pb2.LoadUserRequest(
        user_id=user_id, cash_balance=STARTING_CASH))
    return user_id


def buy(stub, user_id, client_order_id, quantity=1.0):
    return stub.ExecuteOrder(trading_pb2.ExecuteOrderRequest(
        client_order_id=client_order_id,
        user_id=user_id,
        symbol=SYMBOL,
        side="BUY",
        order_type="MARKET",
        quantity=quantity,
    ), timeout=5)


def test_concurrent_orders_for_one_user_do_not_lose_updates(stub, account):
    """The regression test for issue #25.

    Under CheckOrder/UpdateState each order mutated state, released the
    per-user lock, and a later UpdateState overwrote it with a stale snapshot -
    so concurrent orders erased each other's cash deduction and some fills were
    effectively free. ExecuteOrder holds the lock across the whole operation,
    so every fill must get its own sequence number and the final balance must
    account for all of them.
    """
    orders = 20
    with ThreadPoolExecutor(max_workers=orders) as pool:
        responses = list(pool.map(
            lambda i: buy(stub, account, f"race-{i}"), range(orders)))

    filled = [r for r in responses if r.result == trading_pb2.FILLED]
    assert len(filled) == orders

    # Every fill got a distinct sequence number: no gaps, no repeats.
    assert sorted(r.account_sequence for r in filled) == list(range(1, orders + 1))

    # The final fill's balance reflects all 20 deductions, not fewer.
    last = max(filled, key=lambda r: r.account_sequence)
    assert last.new_cash == pytest.approx(STARTING_CASH - orders * PRICE)
    assert last.new_quantity == pytest.approx(float(orders))


def test_duplicate_client_order_id_executes_only_once(stub, account):
    """The regression test for issue #13."""
    first = buy(stub, account, "dup-key")
    second = buy(stub, account, "dup-key")

    assert first.result == trading_pb2.FILLED
    assert second.result == trading_pb2.FILLED

    # The replay returns the original outcome rather than executing again.
    assert second.order_id == first.order_id
    assert second.event_id == first.event_id
    assert second.account_sequence == first.account_sequence
    assert second.new_cash == pytest.approx(first.new_cash)

    # Charged once, not twice.
    assert second.new_cash == pytest.approx(STARTING_CASH - PRICE)


def test_reusing_a_key_for_a_different_order_conflicts(stub, account):
    buy(stub, account, "conflict-key", quantity=1.0)
    clash = buy(stub, account, "conflict-key", quantity=2.0)
    assert clash.result == trading_pb2.IDEMPOTENCY_CONFLICT


def test_unknown_symbol_is_reported_as_such(stub, account):
    response = stub.ExecuteOrder(trading_pb2.ExecuteOrderRequest(
        client_order_id="unknown-1", user_id=account,
        symbol="DEFINITELY_NOT_A_REAL_SYMBOL",
        side="BUY", order_type="MARKET", quantity=1.0), timeout=5)
    assert response.result == trading_pb2.UNKNOWN_SYMBOL


def test_insufficient_funds_reports_the_real_shortfall(stub, account):
    """Regression for issue #26 - this used to come back as 'requires 0'."""
    response = buy(stub, account, "too-big", quantity=1_000.0)
    assert response.result == trading_pb2.INSUFFICIENT_FUNDS
    assert response.required_cash == pytest.approx(1_000.0 * PRICE)
    assert response.available_cash == pytest.approx(STARTING_CASH)


def test_limit_order_that_does_not_cross_is_rejected_distinctly(stub, account):
    response = stub.ExecuteOrder(trading_pb2.ExecuteOrderRequest(
        client_order_id="limit-1", user_id=account, symbol=SYMBOL,
        side="BUY", order_type="LIMIT", quantity=1.0,
        limit_price=PRICE - 10.0), timeout=5)
    assert response.result == trading_pb2.LIMIT_NOT_MET


@pytest.mark.parametrize("quantity", [0.0, -1.0, float("nan"), float("inf")])
def test_engine_rejects_malformed_quantities(stub, account, quantity):
    """The engine validates independently of the HTTP layer."""
    response = buy(stub, account, f"bad-{quantity}", quantity=quantity)
    assert response.result == trading_pb2.INVALID_ORDER
