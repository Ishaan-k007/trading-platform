"""One user must never see or move another user's money.

Every other test in this suite mocks the database, which means none of them
would notice if a query stopped filtering by user. These run against a real
(in-memory SQLite) database with two funded accounts, so a missing
`filter_by(user_id=...)` fails them.

The protection itself is structural: no route accepts a user id as input. Every
one derives it from the verified JWT via `get_jwt_identity()` and scopes its
query to that. There is nothing for a caller to tamper with - which is exactly
the property worth pinning down before someone "helpfully" adds a
`?user_id=` parameter.
"""
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from config import Config
from extensions import db
from models.account import Account
from models.order import Order
from models.position import Position
from models.user import User
from core.money import ACCOUNT_CURRENCY
from enums import OrderStatus


@pytest.fixture
def app(monkeypatch):
    # Config reads DATABASE_URL at import time, so setting the env var here
    # would be too late - patch the class attribute create_app() actually
    # reads. SQLite keeps these tests runnable with no Docker or Postgres.
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "SQLALCHEMY_ENGINE_OPTIONS", {})
    application = create_app()
    application.config.update(TESTING=True)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(username: str, cash: str, symbol: str, quantity: str) -> User:
    user = User(email=f"{username}@test.local", username=username,
                password_hash="x")
    db.session.add(user)
    db.session.flush()

    db.session.add(Account(user_id=user.id, cash_balance=Decimal(cash),
                           currency=ACCOUNT_CURRENCY))
    db.session.add(Position(user_id=user.id, symbol=symbol,
                            quantity=Decimal(quantity),
                            average_price=Decimal("100")))
    db.session.add(Order(id=f"order-{username}", user_id=user.id, symbol=symbol,
                         side="BUY", order_type="MARKET",
                         quantity=Decimal(quantity), filled_price=Decimal("100"),
                         status=OrderStatus.FILLED,
                         idempotency_key=f"key-{username}"))
    db.session.commit()
    return user


@pytest.fixture
def two_users(app):
    """Alice: 1,000 cash and 5 BTCUSDT. Bob: 9,999 cash and 42 ETHUSDT."""
    alice = _make_user("alice", "1000", "BTCUSDT", "5")
    bob = _make_user("bob", "9999", "ETHUSDT", "42")
    return alice, bob


def _headers(app, user):
    with app.app_context():
        return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


def test_portfolio_returns_only_the_callers_account(client, app, two_users):
    alice, _bob = two_users
    app.risk_engine.get_price = lambda symbol: {"symbol": symbol, "price": 100.0,
                                                "updated_at": "t"}

    body = client.get("/api/v1/portfolio", headers=_headers(app, alice)).get_json()

    assert body["cash_balance"] == 1000.0          # Alice's, not Bob's 9,999
    symbols = [p["symbol"] for p in body["positions"]]
    assert symbols == ["BTCUSDT"]
    assert "ETHUSDT" not in symbols


def test_orders_returns_only_the_callers_orders(client, app, two_users):
    alice, _bob = two_users

    body = client.get("/api/v1/orders", headers=_headers(app, alice)).get_json()

    ids = [o["order_id"] for o in body["orders"]]
    assert ids == ["order-alice"]
    assert "order-bob" not in ids


def test_each_user_sees_their_own_balance(client, app, two_users):
    """The mirror image - proves the first test is not passing by accident."""
    alice, bob = two_users
    app.risk_engine.get_price = lambda symbol: {"symbol": symbol, "price": 100.0,
                                                "updated_at": "t"}

    alice_body = client.get("/api/v1/portfolio", headers=_headers(app, alice)).get_json()
    bob_body = client.get("/api/v1/portfolio", headers=_headers(app, bob)).get_json()

    assert alice_body["cash_balance"] == 1000.0
    assert bob_body["cash_balance"] == 9999.0
    assert [p["symbol"] for p in bob_body["positions"]] == ["ETHUSDT"]


def test_a_user_id_in_the_request_body_is_ignored(client, app, two_users):
    """Placing an order cannot be redirected onto someone else's account.

    The route takes user_id from the JWT and never reads it from the body, so a
    smuggled user_id must have no effect. Asserted on the value handed to the
    order service.
    """
    alice, bob = two_users
    from unittest.mock import MagicMock
    app.order_service = MagicMock()
    app.order_service.place_order.return_value = MagicMock(
        id="x", symbol="BTCUSDT", side="BUY", quantity=1,
        filled_price=100.0, status="FILLED", order_type="MARKET")

    client.post("/api/v1/orders", headers=_headers(app, alice), json={
        "order_id": "smuggle-1", "symbol": "BTCUSDT", "side": "BUY",
        "quantity": 1, "order_type": "MARKET",
        "user_id": bob.id,          # ignored
    })

    assert app.order_service.place_order.call_args.kwargs["user_id"] == alice.id


def test_no_token_is_rejected(client, app, two_users):
    assert client.get("/api/v1/portfolio").status_code == 401
    assert client.get("/api/v1/orders").status_code == 401


def test_a_forged_token_is_rejected(client, app, two_users):
    forged = {"Authorization": "Bearer not.a.real.token"}
    assert client.get("/api/v1/portfolio", headers=forged).status_code == 422
