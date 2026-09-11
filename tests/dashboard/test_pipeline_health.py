"""Detecting a stalled fill pipeline from the dashboard's two data sources.

The failure this exists for: `fill_consumer` died, so nothing reached
PostgreSQL, but the engine kept filling orders and the runner kept writing
CSVs. The dashboard showed 32 fills on the execution tape next to an untouched
10,000 cash balance and reported everything as healthy, because the two numbers
came from different places and nothing compared them.
"""
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard_data import pipeline_health


def test_matching_counts_are_in_sync():
    result = pipeline_health(tape_fills=10, persisted_fills=10,
                             previous=None, now=0.0)
    assert result["state"] == "synced"
    assert result["gap"] == 0


def test_a_fresh_gap_is_catching_up_not_an_alarm():
    """Normal operation: the database trails by a moment and then catches up."""
    result = pipeline_health(tape_fills=12, persisted_fills=10,
                             previous=None, now=0.0)
    assert result["state"] == "catching-up"
    assert result["gap"] == 2


def test_a_gap_that_closes_stays_quiet():
    first = pipeline_health(10, 8, None, now=0.0)
    second = pipeline_health(12, 11, first, now=30.0)    # database moved 8 -> 11
    third = pipeline_health(12, 12, second, now=40.0)
    assert second["state"] == "catching-up"
    assert third["state"] == "synced"


def test_progress_restarts_the_stall_clock():
    """Any forward movement counts, even if the gap itself grows."""
    first = pipeline_health(10, 5, None, now=0.0)
    stale = pipeline_health(20, 5, first, now=40.0)       # no progress for 40s
    moved = pipeline_health(30, 6, stale, now=41.0)       # one fill landed
    assert moved["stalled_seconds"] == 0.0
    assert moved["state"] == "catching-up"


def test_a_gap_going_nowhere_is_reported_as_stalled():
    """The regression: the consumer is dead and the gap never closes."""
    observation = pipeline_health(32, 0, None, now=0.0)
    assert observation["state"] == "catching-up"          # too early to tell

    observation = pipeline_health(40, 0, observation, now=30.0)
    assert observation["state"] == "catching-up"          # still inside the window

    observation = pipeline_health(52, 0, observation, now=60.0)
    assert observation["state"] == "stalled"
    assert observation["gap"] == 52
    assert observation["stalled_seconds"] == 60.0


def test_recovery_clears_the_alarm():
    """Restarting the consumer drains the backlog and the alarm goes away."""
    observation = pipeline_health(52, 0, None, now=0.0)
    observation = pipeline_health(52, 0, observation, now=60.0)
    assert observation["state"] == "stalled"

    observation = pipeline_health(52, 52, observation, now=70.0)
    assert observation["state"] == "synced"
    assert observation["stalled_seconds"] == 0.0


def test_an_unreadable_database_is_unknown_not_stalled():
    """A failed read is reported on its own card; do not invent a gap."""
    result = pipeline_health(tape_fills=20, persisted_fills=None,
                             previous=None, now=100.0)
    assert result["state"] == "unknown"
    assert result["gap"] is None


def test_a_database_ahead_of_the_tape_is_not_an_alarm():
    """Possible after wiping the CSVs without wiping the database."""
    result = pipeline_health(tape_fills=3, persisted_fills=40,
                             previous=None, now=0.0)
    assert result["state"] == "synced"


def test_an_idle_system_with_no_fills_is_in_sync():
    result = pipeline_health(tape_fills=0, persisted_fills=0,
                             previous=None, now=0.0)
    assert result["state"] == "synced"


def test_the_stall_threshold_is_configurable():
    observation = pipeline_health(10, 0, None, now=0.0, stall_seconds=5.0)
    observation = pipeline_health(10, 0, observation, now=6.0, stall_seconds=5.0)
    assert observation["state"] == "stalled"


# --- the rendered dashboard -------------------------------------------------

APP = Path(__file__).resolve().parents[2] / "streamlit_app.py"

TRADES = """timestamp,side,symbol,quantity,fill_price
2026-09-11T00:28:12+00:00,BUY,BTCUSDT,0.001,76835.93
2026-09-11T00:28:16+00:00,SELL,BTCUSDT,0.001,76850.82
2026-09-11T00:28:24+00:00,BUY,BTCUSDT,0.001,76836.54
"""

STATE = """timestamp,symbol,price,cash,equity
2026-09-11T00:28:12+00:00,BTCUSDT,76835.93,10000,10000
2026-09-11T00:28:24+00:00,BTCUSDT,76836.54,10000,10000
"""


def _live_app(monkeypatch, tmp_path, persisted_fills):
    """A live-mode dashboard with three fills on the tape and a chosen DB count."""
    import dashboard_ui

    (tmp_path / "strategy_trades.csv").write_text(TRADES, encoding="utf-8")
    (tmp_path / "strategy_state.csv").write_text(STATE, encoding="utf-8")
    monkeypatch.setattr(dashboard_ui, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        dashboard_ui, "live_quotes",
        lambda: [{"symbol": "BTCUSDT", "reachable": True, "price": 76840.0,
                  "latency_ms": 1.0, "sample_id": 1}])
    monkeypatch.setattr(
        dashboard_ui, "live_database_status",
        lambda: {"online": True, "account_found": True, "fills": persisted_fills,
                 "last_fill": None, "currency": "USDT"})
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["username"] = "dashboard-test"
    return app


def test_a_healthy_pipeline_shows_no_alarm(monkeypatch, tmp_path):
    app = _live_app(monkeypatch, tmp_path, persisted_fills=3).run()
    assert not app.exception
    content = " ".join(m.value for m in app.markdown)
    assert "IN SYNC" in content
    assert "FILL PIPELINE STALLED" not in content


def test_a_stalled_pipeline_raises_the_alarm(monkeypatch, tmp_path):
    """Three fills on the tape, none in the database, and no progress.

    This is the shape of the real incident: the consumer was dead, so the
    dashboard was showing fills alongside an untouched cash balance.
    """
    app = _live_app(monkeypatch, tmp_path, persisted_fills=0)
    # Pre-seed an observation that is already past the stall window, standing in
    # for the dashboard having watched the gap go nowhere across refreshes.
    app.session_state["pipeline_health"] = {
        "state": "catching-up", "gap": 3, "persisted": 0, "tape": 3,
        "stalled_seconds": 0.0, "progress_at": time.monotonic() - 600,
    }
    app.run()

    assert not app.exception
    content = " ".join(m.value for m in app.markdown)
    assert "FILL PIPELINE STALLED" in content
    assert "STALLED" in content
    assert "fill_consumer" in content       # tells the reader where to look


def test_the_card_shows_both_sides_of_the_pipeline(monkeypatch, tmp_path):
    """'Persisted fills' reads database / tape, so a divergence is visible."""
    app = _live_app(monkeypatch, tmp_path, persisted_fills=1).run()
    assert not app.exception
    content = " ".join(m.value for m in app.markdown)
    assert "1 / 3" in content
