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
    


    
    
    
    