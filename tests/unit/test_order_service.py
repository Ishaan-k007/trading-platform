"""OrderService maps every engine result code to the right domain exception.

The pre-ExecuteOrder code could not do this: CheckOrder returned a bool plus a
free-text reason that Python never inspected, so every rejection surfaced as
InsufficientFundsError. These tests pin the typed mapping in place.
"""
from unittest.mock import MagicMock

import pytest

from core.exceptions import (
    DuplicateRequestError,
    InsufficientFundsError,
    InsufficientPositionError,
    InvalidOrderError,
    LimitNotMetError,
    SymbolNotFoundError,
)
from services import trading_pb2
from services.order_service import OrderService


def response(code, **extra) -> dict:
    """A full execute_order() return dict, defaulted, with overrides applied."""
    base = {
        "result": code,
        "result_name": trading_pb2.OrderResultCode.Name(code),
        "order_id": "srv-1",
        "event_id": "evt-1",
        "client_order_id": "cli-1",
        "fill_price": 0.0,
        "market_price": 100.0,
        "required_cash": 0.0,
        "available_cash": 0.0,
        "required_quantity": 0.0,
        "available_quantity": 0.0,
        "new_cash": 0.0,
        "new_quantity": 0.0,
        "account_sequence": 0,
        "message": "",
    }
    base.update(extra)
    return base


def make_service(result: dict) -> OrderService:
    engine = MagicMock()
    engine.has_user.return_value = True      # skip the Postgres hydration path
    engine.execute_order.return_value = result
    return OrderService(engine)


def place(service):
    return service.place_order(
        user_id=1, order_id="cli-1", side="BUY", symbol="BTCUSDT",
        quantity=1.0, order_type="MARKET", limit_price=None,
    )


def test_filled_returns_order_built_from_engine_response():
    svc = make_service(response(trading_pb2.FILLED, fill_price=250.5, new_cash=9_749.5))
    order = place(svc)
    assert order.id == "srv-1"                  # engine's canonical id, not a Python uuid
    assert order.idempotency_key == "cli-1"     # client's key, for the DB unique constraint
    assert float(order.filled_price) == 250.5
    assert order.status == "FILLED"


def test_filled_passes_client_order_id_through_unchanged():
    svc = make_service(response(trading_pb2.FILLED, fill_price=1.0))
    place(svc)
    kwargs = svc.risk_engine.execute_order.call_args.kwargs
    assert kwargs["client_order_id"] == "cli-1"


def test_unknown_symbol_raises_symbol_not_found():
    with pytest.raises(SymbolNotFoundError):
        place(make_service(response(trading_pb2.UNKNOWN_SYMBOL)))


def test_limit_not_met_has_its_own_error():
    """Regression for #26 - this used to be reported as insufficient funds."""
    with pytest.raises(LimitNotMetError):
        place(make_service(response(trading_pb2.LIMIT_NOT_MET)))


def test_insufficient_funds_reports_the_engine_s_numbers():
    """Regression for #26 - the old code always said 'Order requires 0'."""
    svc = make_service(response(
        trading_pb2.INSUFFICIENT_FUNDS, required_cash=500.0, available_cash=100.0))
    with pytest.raises(InsufficientFundsError) as exc:
        place(svc)
    assert "500" in str(exc.value)
    assert "100" in str(exc.value)


def test_insufficient_position_reports_the_engine_s_numbers():
    svc = make_service(response(
        trading_pb2.INSUFFICIENT_POSITION, required_quantity=5.0, available_quantity=2.0))
    with pytest.raises(InsufficientPositionError) as exc:
        place(svc)
    assert "5" in str(exc.value)
    assert "2" in str(exc.value)


def test_idempotency_conflict_raises_duplicate_request():
    with pytest.raises(DuplicateRequestError):
        place(make_service(response(trading_pb2.IDEMPOTENCY_CONFLICT)))


def test_invalid_order_raises_invalid_order():
    with pytest.raises(InvalidOrderError):
        place(make_service(response(trading_pb2.INVALID_ORDER, message="bad quantity")))
