from flask import Flask
from config import Config
from extensions import db, jwt, bcrypt, migrate
from core.middleware import register_error_handlers
from services.risk_engine_client import RiskEngineClient
from routes.market_routes import market_bp
from routes.auth_routes import auth_bp
from models import user, account, order, position, ledger_entry, market_price, risk_check
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialise extensions 
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    

    # Register blueprints
   
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(market_bp, url_prefix="/api/v1/market")
    
    
    # Register error handlers
    register_error_handlers(app)

    app.risk_engine = RiskEngineClient(app.config["RISK_ENGINE_HOST"],app.config["RISK_ENGINE_PORT"])
    
    
    
    


    return app

    
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
