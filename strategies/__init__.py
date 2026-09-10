"""Pluggable trading strategies.

Strategies here must stay free of Flask/SQLAlchemy/gRPC imports — they only
see prices and emit OrderIntents (see base.py). That's what lets the same
strategy class run unmodified from strategy_runner.py today and, later,
from a backtester fed historical data instead of live prices.
"""
