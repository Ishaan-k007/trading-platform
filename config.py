import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Recover transparently from connections dropped while idle (Postgres idle
    # timeout, container restart, laptop sleep). pool_pre_ping runs a lightweight
    # "SELECT 1" before handing out a pooled connection and reconnects if it is
    # dead; pool_recycle retires connections older than 30 minutes.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "order-fills")
    KAFKA_MARKET_TOPIC = os.getenv("KAFKA_MARKET_TOPIC", "market-ticks")
    
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 900))
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 604800))
    RISK_ENGINE_HOST = os.getenv("RISK_ENGINE_HOST", "localhost")
    RISK_ENGINE_PORT = int(os.getenv("RISK_ENGINE_PORT", 50051))
    WAL_PATH = os.getenv("WAL_PATH", "wal.log")
