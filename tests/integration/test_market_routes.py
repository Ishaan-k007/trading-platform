import pytest
from unittest.mock import MagicMock
from app import create_app
from core.exceptions import RiskEngineUnavailableError, SymbolNotFoundError

@pytest.fixture
def app():
    app = create_app()
    app.risk_engine = MagicMock()
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_get_all_prices_returns_200(client, app):
    app.risk_engine.get_all_prices.return_value = {"AAPL": 182.5, "MSFT": 415.0}
    response = client.get("/api/v1/market/prices")
    assert response.status_code == 200
    data = response.get_json()
    assert data["prices"] == {"AAPL": 182.5, "MSFT": 415.0}
def test_get_price_by_symbol_returns_200(client, app):
    app.risk_engine.get_price.return_value = {"symbol": "AAPL", "price": 182.5, "updated_at": "2024-06-01"}
    response = client.get("/api/v1/market/prices/AAPL")
    assert response.status_code == 200
    data = response.get_json()
    assert data["price"] == 182.5



def test_get_price_unknown_symbol_returns_404(client, app): 
    app.risk_engine.get_price.side_effect = SymbolNotFoundError("FAKE")
    response = client.get("/api/v1/market/prices/FAKE")
    assert response.status_code == 404
def test_get_all_prices_risk_engine_unavailable_returns_503(client, app):
    app.risk_engine.get_all_prices.side_effect = RiskEngineUnavailableError()
    response = client.get("/api/v1/market/prices")
    assert response.status_code == 503
    