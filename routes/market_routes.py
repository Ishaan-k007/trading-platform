from flask import Blueprint, jsonify, current_app
from core.exceptions import RiskEngineUnavailableError, SymbolNotFoundError

market_bp = Blueprint('market', __name__)

@market_bp.route('/prices', methods=['GET'])
def get_all_prices():
    """Return current prices for all tracked symbols.

    Returns:
        200 with {"prices": {symbol: price}} on success.
        503 if the risk engine is unreachable.
    """
    prices = current_app.risk_engine.get_all_prices()
    return jsonify({"prices": prices}), 200


@market_bp.route('/prices/<symbol>', methods=['GET'])
def get_price(symbol):
    """Return the current price for a single symbol.

    Args:
        symbol: Stock ticker from the URL path e.g. 'AAPL'.

    Returns:
        200 with {"symbol", "price", "updated_at"} on success.
        404 if the symbol is not recognised.
        503 if the risk engine is unreachable.
    """
    result = current_app.risk_engine.get_price(symbol.upper())
    return jsonify(result), 200

