from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from models.order import Order
from models.position import Position
from models.account import Account

portfolio_bp = Blueprint("portfolio_bp", __name__)

@portfolio_bp.route("/portfolio", methods=["GET"])
@jwt_required()
def get_portfolio():
    user_id = int(get_jwt_identity())
    # Implementation for fetching portfolio data
    account = Account.query.filter_by(user_id=user_id).first()
    if not account:
        return jsonify({"error": "Account not found"}), 404
    positions = Position.query.filter_by(user_id=user_id).all()
    for position in positions:
        price_data = current_app.risk_engine.get_price(position.symbol)
        position.current_price = price_data["price"]
        position.market_value = position.current_price * position.quantity
    return jsonify({
        "cash_balance": float(account.cash_balance),
        "positions": [
            {
                "symbol": position.symbol,
                "quantity": float(position.quantity),
                "average_price": float(position.average_price),
                "current_price": float(position.current_price),
                "market_value": float(position.market_value)
            } for position in positions
        ]
    }), 200
    
@portfolio_bp.route("/orders", methods=["GET"])
@jwt_required()
def get_orders():
    user_id = int(get_jwt_identity())
    orders = Order.query.filter_by(user_id=user_id).all()
    return jsonify({
        "orders": [
            {
                "order_id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": float(order.quantity),
                "fill_price": float(order.filled_price),
                "status": order.status,
                "order_type": order.order_type
            } for order in orders
        ]
    }), 200



