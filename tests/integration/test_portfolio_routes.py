from flask_jwt_extended import create_access_token
import pytest
from unittest.mock import MagicMock, patch
from app import create_app
from core.exceptions import RiskEngineUnavailableError

@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.risk_engine = MagicMock()
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity="1")
    return {"Authorization": f"Bearer {token}"}

def test_get_portfolio_no_jwt(client, app):
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 401

@patch("routes.portfolio_routes.Account.query")
@patch("routes.portfolio_routes.Position.query")
def test_get_portfolio_returns_200(mock_position_query, mock_account_query, client, app, auth_headers):
    mock_account_query.filter_by.return_value.first.return_value = MagicMock(cash_balance=1000.0)
    mock_position_query.filter_by.return_value.all.return_value = [
    MagicMock(symbol="AAPL", quantity=10, average_price=150.0),
]

    
    app.risk_engine.get_price.return_value = {"symbol": "AAPL", "price": 180.0, "updated_at": "2026-07-08"}

    
    response = client.get("/api/v1/portfolio", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["cash_balance"] == 1000.0
    assert len(data["positions"]) == 1
    
def test_get_orders_no_jwt(client, app):
    response = client.get("/api/v1/orders")
    assert response.status_code == 401

def test_get_orders_returns_200(client, app, auth_headers):
    with patch("routes.portfolio_routes.Order.query") as mock_order_query:
        mock_order_query.filter_by.return_value.all.return_value = [
            MagicMock(id="abc-123", symbol="AAPL", side="BUY", quantity=10, filled_price=182.5, status="FILLED", order_type="MARKET"),
        ]
        response = client.get("/api/v1/orders", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["orders"]) == 1
        assert data["orders"][0]["order_id"] == "abc-123"
@patch("routes.portfolio_routes.Account.query")
@patch("routes.portfolio_routes.Position.query")
def test_get_portfolio_risk_engine_unavailable(mock_position_query, mock_account_query, client, app, auth_headers):
    mock_account_query.filter_by.return_value.first.return_value = MagicMock(cash_balance=1000.0)
    mock_position_query.filter_by.return_value.all.return_value = [
        MagicMock(symbol="AAPL", quantity=10, average_price=150.0),
    ]
    app.risk_engine.get_price.side_effect = RiskEngineUnavailableError()
    response = client.get("/api/v1/portfolio", headers=auth_headers)
    assert response.status_code == 503