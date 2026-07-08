from flask import Blueprint, request, jsonify, current_app 
from flask_jwt_extended import jwt_required, get_jwt_identity
  
  
order_bp = Blueprint("order_bp", __name__)

@order_bp.route("", methods=["POST"])
@jwt_required()
def place_order():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON in request"}), 400
    if "symbol" not in data or "side" not in data or "quantity" not in data or "order_type" not in data or "order_id" not in data :
        return jsonify({"error": "Missing required fields"}), 400
    if data["side"] not in ["BUY", "SELL"]:
        return jsonify({"error": "Invalid side. Must be 'BUY' or 'SELL'"}), 400
    if data["order_type"] not in ["MARKET", "LIMIT"]:
        return jsonify({"error": "Invalid order type. Must be 'MARKET' or 'LIMIT'"}), 400
    if data["order_type"] == "LIMIT" and "limit_price" not in data:
        return jsonify({"error": "Missing limit_price for LIMIT order"}), 400
    if data["quantity"] <= 0:
        return jsonify({"error": "Quantity must be greater than 0"}), 400
   
    order = current_app.order_service.place_order(user_id = user_id, order_id = data["order_id"],  side = data["side"], symbol = data["symbol"], quantity = data["quantity"], order_type = data["order_type"], limit_price = data.get("limit_price"))
    
  
    return jsonify({
    "order_id": order.id,
    "symbol": order.symbol,
    "side": order.side,
    "quantity": float(order.quantity),
    "fill_price": float(order.filled_price),
    "status": order.status,
    "order_type": order.order_type,
        }), 201

    



