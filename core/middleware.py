from flask import Flask, jsonify
from core.exceptions import TradingError


def register_error_handlers(app: Flask) -> None:

    @app.errorhandler(TradingError)
    def handle_trading_error(e: TradingError):
        return jsonify({"error": {"code": e.error_code, "message": str(e)}}), e.http_status

    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Resource not found."}}), 404

    @app.errorhandler(405)
    def handle_405(e):
        return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": "Method not allowed."}}), 405

    @app.errorhandler(500)
    def handle_500(e):
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}}), 500
