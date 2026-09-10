import math

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from core.exceptions import InvalidOrderError

order_bp = Blueprint("order_bp", __name__)

REQUIRED_FIELDS = ("order_id", "symbol", "side", "quantity", "order_type")


def _positive_number(value, field: str) -> float:
    """Return `value` as a finite float greater than zero, or raise.

    Written as an explicit type-and-finiteness check rather than `value <= 0`,
    because that check has two holes:

    - JSON permits the bare literals ``NaN`` and ``Infinity``, and Python's
      json module accepts them. Every comparison involving NaN is False, so
      ``NaN <= 0`` is False and a NaN quantity sails straight through.
    - A string quantity raises TypeError from the same comparison, which
      surfaces as a 500 rather than a 400.

    The C++ engine rejects both cases as INVALID_ORDER regardless - it is the
    last line of defence and does not trust its callers - but the API should
    not be leaning on that for a plainly malformed request.
    """
    # bool is a subclass of int in Python, so `True` would otherwise become 1.0.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidOrderError(f"{field} must be a number.")
    value = float(value)
    if not math.isfinite(value):
        raise InvalidOrderError(f"{field} must be a finite number.")
    if value <= 0:
        raise InvalidOrderError(f"{field} must be greater than 0.")
    return value


@order_bp.route("", methods=["POST"])
@jwt_required()
def place_order():
    user_id = int(get_jwt_identity())

    data = request.get_json(silent=True)
    if not data:
        raise InvalidOrderError("Missing JSON in request.")

    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        raise InvalidOrderError(f"Missing required fields: {', '.join(missing)}.")

    if not isinstance(data["order_id"], str) or not data["order_id"].strip():
        raise InvalidOrderError("order_id must be a non-empty string.")
    if not isinstance(data["symbol"], str) or not data["symbol"].strip():
        raise InvalidOrderError("symbol must be a non-empty string.")
    if data["side"] not in ("BUY", "SELL"):
        raise InvalidOrderError("Invalid side. Must be 'BUY' or 'SELL'.")
    if data["order_type"] not in ("MARKET", "LIMIT"):
        raise InvalidOrderError("Invalid order type. Must be 'MARKET' or 'LIMIT'.")

    quantity = _positive_number(data["quantity"], "quantity")

    limit_price = None
    if data["order_type"] == "LIMIT":
        if "limit_price" not in data:
            raise InvalidOrderError("Missing limit_price for LIMIT order.")
        limit_price = _positive_number(data["limit_price"], "limit_price")

    order = current_app.order_service.place_order(
        user_id=user_id,
        order_id=data["order_id"],
        side=data["side"],
        symbol=data["symbol"],
        quantity=quantity,
        order_type=data["order_type"],
        limit_price=limit_price,
    )

    return jsonify({
        "order_id": order.id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": float(order.quantity),
        "fill_price": float(order.filled_price),
        "status": order.status,
        "order_type": order.order_type,
    }), 201
