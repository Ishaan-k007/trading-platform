from flask_jwt_extended import create_access_token
import pytest
from unittest.mock import MagicMock
from app import create_app
from core.exceptions import InsufficientFundsError, InsufficientPositionError, SymbolNotFoundError, RiskEngineUnavailableError

@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.order_service = MagicMock()
    return app

@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity="1")
    return {"Authorization": f"Bearer {token}"}

def test_place_order_returns_201(client, app, auth_headers):
    app.order_service.place_order.return_value = MagicMock(id = "abc-123", symbol = "AAPL", side = "BUY", quantity = 10, filled_price = 182.5, status = "FILLED", order_type = "MARKET")
    response = client.post("/api/v1/orders", json = {"order_id": "abc-123",  "symbol" : "AAPL", "side" : "BUY", "quantity" : 10, "order_type" : "MARKET"}, headers = auth_headers)
    assert response.status_code == 201
    data = response.get_json()
    assert data["order_id"] == "abc-123"

def test_no_JWT_token(client,app):
    app.order_service.place_order.return_value = MagicMock(id = "abc-123", symbol = "AAPL", side = "BUY", quantity = 10, filled_price = 182.5, status = "FILLED", order_type = "MARKET")
    response = client.post("/api/v1/orders", json = {"order_id": "abc-123",  "symbol" : "AAPL", "side" : "BUY", "quantity" : 10, "order_type" : "MARKET"})
    assert response.status_code == 401
    

def test_missing_field(client,app,auth_headers):
    app.order_service.place_order.return_value = MagicMock(id = "abc-123", symbol = "AAPL", side = "BUY", quantity = 10, filled_price = 182.5, status = "FILLED", order_type = "MARKET")
    response = client.post("/api/v1/orders", json = {"order_id": "abc-123", "side" : "BUY", "quantity" : 10, "order_type" : "MARKET"}, headers = auth_headers)
    assert response.status_code == 400
    
def test_invalid_side(client,app,auth_headers):
    app.order_service.place_order.return_value = MagicMock(id = "abc-123", symbol = "AAPL", side = "BUY", quantity = 10, filled_price = 182.5, status = "FILLED", order_type = "MARKET")
    response = client.post("/api/v1/orders", json = {"order_id": "abc-123",  "symbol" : "AAPL", "side" : "HOLD", "quantity" : 10, "order_type" : "MARKET"}, headers = auth_headers)
    assert response.status_code == 400


def test_symbol_not_found(client,app,auth_headers):
    app.order_service.place_order.side_effect = SymbolNotFoundError("FAKE")
    response = client.post("/api/v1/orders", json = {"order_id": "abc-123",  "symbol" : "AAPL", "side" : "BUY", "quantity" : 10, "order_type" : "MARKET"}, headers = auth_headers)
    assert response.status_code == 404

def test_insufficient_funds(client,app,auth_headers):
    app.order_service.place_order.side_effect = InsufficientFundsError(balance=100, required=500)
    response = client.post("/api/v1/orders", json = {"order_id": "abc-123",  "symbol" : "AAPL", "side" : "BUY", "quantity" : 10, "order_type" : "MARKET"}, headers = auth_headers)
    assert response.status_code == 402


# --- request validation -------------------------------------------------
#
# The HTTP layer must agree with the engine about what a malformed order is.
# Before these, `quantity <= 0` was the only check: NaN and Infinity passed it
# (every NaN comparison is False) and a string quantity raised TypeError, which
# surfaced as a 500 instead of a 400.

def _order(**overrides):
    body = {"order_id": "abc-123", "symbol": "AAPL", "side": "BUY",
            "quantity": 10, "order_type": "MARKET"}
    body.update(overrides)
    return body


@pytest.mark.parametrize("bad_quantity", [
    float("nan"), float("inf"), float("-inf"), 0, -5, "10", None, True,
])
def test_malformed_quantity_is_rejected_with_400(client, app, auth_headers, bad_quantity):
    app.order_service.place_order.return_value = MagicMock()
    response = client.post("/api/v1/orders", json=_order(quantity=bad_quantity),
                           headers=auth_headers)
    assert response.status_code == 400
    app.order_service.place_order.assert_not_called()


def test_nan_quantity_never_reaches_the_service(client, app, auth_headers):
    """The specific hole: NaN <= 0 is False, so the old check let it through."""
    app.order_service.place_order.return_value = MagicMock()
    response = client.post("/api/v1/orders", json=_order(quantity=float("nan")),
                           headers=auth_headers)
    assert response.status_code == 400
    app.order_service.place_order.assert_not_called()


def test_string_quantity_is_a_400_not_a_500(client, app, auth_headers):
    """Comparing a str to an int raised TypeError, i.e. an unhandled 500."""
    response = client.post("/api/v1/orders", json=_order(quantity="abc"),
                           headers=auth_headers)
    assert response.status_code == 400


def test_blank_order_id_is_rejected(client, app, auth_headers):
    """order_id is the idempotency key - an empty one makes retries unmatchable."""
    response = client.post("/api/v1/orders", json=_order(order_id="   "),
                           headers=auth_headers)
    assert response.status_code == 400


def test_limit_order_without_a_price_is_rejected(client, app, auth_headers):
    response = client.post("/api/v1/orders", json=_order(order_type="LIMIT"),
                           headers=auth_headers)
    assert response.status_code == 400


@pytest.mark.parametrize("bad_price", [0, -1, float("nan"), float("inf")])
def test_malformed_limit_price_is_rejected(client, app, auth_headers, bad_price):
    response = client.post(
        "/api/v1/orders",
        json=_order(order_type="LIMIT", limit_price=bad_price),
        headers=auth_headers)
    assert response.status_code == 400


def test_errors_use_the_standard_error_shape(client, app, auth_headers):
    """Same {"error": {"code", "message"}} envelope as every other failure."""
    response = client.post("/api/v1/orders", json=_order(quantity=0),
                           headers=auth_headers)
    body = response.get_json()
    assert body["error"]["code"] == "INVALID_ORDER"
    assert "quantity" in body["error"]["message"]
    


    
    
    
    