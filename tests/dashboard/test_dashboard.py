"""Read-only UI regression checks; no running trading services required."""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from dashboard_data import (
    age_seconds,
    database_status,
    read_log,
    sample_session,
    summarize_trades,
)

APP = Path(__file__).resolve().parents[2] / "streamlit_app.py"


def test_reader_waits_for_partial_final_line(tmp_path):
    path = tmp_path / "strategy_state.csv"
    path.write_bytes(
        b"timestamp,symbol,price,cash,equity\n2026-01-01T00:00:00Z,BTCUSDT,100,1000,1000\n2026-01-01T00:00:02Z,BTC"
    )
    frame, warnings = read_log(path, "state")
    assert len(frame) == 1
    assert not warnings


def test_reader_reports_invalid_values(tmp_path):
    path = tmp_path / "strategy_trades.csv"
    path.write_text(
        "timestamp,side,symbol,quantity,fill_price\n2026-01-01T00:00:00Z,BUY,BTCUSDT,1,100\n2026-01-01T00:00:01Z,BUY,BTCUSDT,-1,inf\n"
    )
    frame, warnings = read_log(path, "trades")
    assert len(frame) == 1
    assert "1 invalid" in warnings[0]


def test_matching_is_per_symbol_and_handles_partial_exits():
    rows = [
        (0, "BUY", "BTCUSDT", 2, 100),
        (1, "BUY", "ETHUSDT", 1, 200),
        (2, "SELL", "ETHUSDT", 1, 220),
        (3, "SELL", "BTCUSDT", 0.5, 90),
    ]
    trades = pd.DataFrame(
        rows, columns=["timestamp", "side", "symbol", "quantity", "fill_price"]
    )
    summary = summarize_trades(trades)
    assert summary["realized"] == pytest.approx(15)
    assert summary["win_rate"] == 50
    assert summary["positions"]["BTCUSDT"]["quantity"] == 1.5
    assert "ETHUSDT" not in summary["positions"]


def test_incomplete_history_does_not_claim_win_rate():
    trades = pd.DataFrame(
        [(0, "SELL", "BTCUSDT", 1, 100)],
        columns=["timestamp", "side", "symbol", "quantity", "fill_price"],
    )
    assert summarize_trades(trades)["win_rate"] is None
    assert summarize_trades(trades)["incomplete"]


def test_sample_is_self_consistent_and_explicitly_identified():
    state, trades, market = sample_session()
    summary = summarize_trades(trades)
    assert len(trades) == 4 and not summary["positions"]
    assert state.iloc[-1].equity == pytest.approx(10000 + summary["realized"])
    assert (trades.order_id.str.startswith("SAMPLE-")).all()
    assert (market.best_bid < market.best_ask).all()


def test_timestamp_freshness_does_not_accept_invalid_or_future_time():
    now = pd.Timestamp("2026-01-01T00:00:00Z")
    assert age_seconds("invalid", now) is None
    assert age_seconds("2026-01-02T00:00:00Z", now) is None
    assert age_seconds("2025-12-31T23:59:50Z", now) == 10


def test_database_error_is_redacted():
    class BrokenEngine:
        def connect(self):
            raise RuntimeError("postgresql://user:secret-password@host/db")

    result = database_status(BrokenEngine(), "strategy_bot")
    assert result["online"] is False
    assert "secret" not in str(result)


def test_sample_playback_advances_and_restarts_without_backend(monkeypatch):
    import dashboard_ui

    def forbidden():
        raise AssertionError("Sample playback must not access the backend")

    monkeypatch.setattr(dashboard_ui, "live_quotes", forbidden)
    monkeypatch.setattr(dashboard_ui, "live_database_status", forbidden)
    app = AppTest.from_file(str(APP), default_timeout=15)
    app.session_state["sample_preview"] = True
    app.run()
    assert not app.exception
    assert any("SAMPLE WALKTHROUGH" in m.value for m in app.markdown)
    assert any(m.label == "Visible fills" and m.value == "1" for m in app.metric)
    app.button(key="next_fill").click().run()
    assert not app.exception
    assert any(m.label == "Visible fills" and m.value == "2" for m in app.metric)
    app.button(key="restart_replay").click().run()
    assert not app.exception
    assert any(m.label == "Visible fills" and m.value == "0" for m in app.metric)
    app.slider(key="replay_frame").set_value(66).run()
    assert not app.exception
    assert any(m.label == "Visible fills" and m.value == "4" for m in app.metric)
    assert app.button(key="next_fill").disabled


def test_live_empty_backend_keeps_market_and_health_visible(monkeypatch, tmp_path):
    import dashboard_ui

    monkeypatch.setattr(dashboard_ui, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        dashboard_ui,
        "live_quotes",
        lambda: [{"symbol": "BTCUSDT", "reachable": False, "error": "Unavailable"}],
    )
    monkeypatch.setattr(
        dashboard_ui,
        "live_database_status",
        lambda: {"online": False, "fills": None, "last_fill": None, "currency": None},
    )
    app = AppTest.from_file(str(APP), default_timeout=15)
    app.session_state["username"] = "dashboard-test"
    app.run()
    assert not app.exception
    content = " ".join(m.value for m in app.markdown)
    assert (
        "Market watch" in content
        and "System pulse" in content
        and "UNAVAILABLE" in content
    )
    assert any("Waiting for strategy observations" in m.value for m in app.info)


def test_login_offers_sample_without_backend():
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    app.button(key="open_sample").click().run()
    assert not app.exception
    assert any("SAMPLE WALKTHROUGH" in m.value for m in app.markdown)
