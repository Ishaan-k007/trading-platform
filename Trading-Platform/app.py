from flask import Flask
from config import Config
from extensions import db, jwt, bcrypt, migrate
from core.middleware import register_error_handlers


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialise extensions 
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    # Import models so Alembic can detect them
    from models import user, account, order, position, ledger_entry, market_price, risk_check

    # Register blueprints
    from routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")

    # Register error handlers
    register_error_handlers(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
