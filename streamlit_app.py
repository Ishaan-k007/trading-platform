"""Live dashboard for the strategy_runner.py demo.

Reads the CSV logs strategy_runner.py writes - no direct DB or gRPC access
here, so the dashboard can run (and be iterated on) independently of
whether the rest of the stack is up.

Usage:
    poetry run streamlit run streamlit_app.py
"""
import os
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy.exc import IntegrityError

from app import create_app
from core.exceptions import InvalidCredentialsError
from services.auth_service import AuthService

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
STATE_LOG_PATH = os.path.join(LOG_DIR, "strategy_state.csv")
TRADES_LOG_PATH = os.path.join(LOG_DIR, "strategy_trades.csv")
REFRESH_SECONDS = 3

# Bloomberg-terminal-inspired palette: black background, amber for
# headers/labels, cyan for equity, white for price, saturated green/red
# for buy/sell and gains/losses. Kept purposeful rather than a rainbow -
# amber is reserved for chrome, cyan/white distinguish the two charts.
COLOR_AMBER = "#FFA500"
COLOR_CYAN = "#22D3EE"
COLOR_WHITE = "#E8E8E8"
COLOR_GREEN = "#00E676"
COLOR_RED = "#FF3B30"
COLOR_GRID = "rgba(255, 165, 0, 0.10)"
COLOR_MUTED = "#8B8B8B"
MONO_FONT = "'Consolas', 'SFMono-Regular', Menlo, monospace"

st.set_page_config(page_title="Strategy Demo", layout="wide")

st.markdown(f"""
<style>
html, body, [class*="css"] {{ font-family: {MONO_FONT}; }}
h1 {{ color: {COLOR_AMBER} !important; letter-spacing: 2px; font-weight: 700;
     text-shadow: 0 0 18px rgba(255, 165, 0, 0.35); }}
h2, h3 {{ color: {COLOR_WHITE} !important; text-transform: uppercase;
          letter-spacing: 2px; font-size: 0.95rem !important; font-weight: 700;
          border-bottom: 1px solid rgba(255, 165, 0, 0.25); padding-bottom: 6px; }}
[data-testid="stMetricLabel"] {{ text-transform: uppercase; letter-spacing: 1.5px;
                                  font-size: 0.7rem; color: {COLOR_MUTED}; }}
[data-testid="stMetricValue"] {{ font-family: {MONO_FONT}; font-weight: 700; }}
.status-banner {{ font-family: {MONO_FONT}; letter-spacing: 1.5px; text-transform: uppercase;
                   font-size: 0.85rem; font-weight: 700; padding: 10px 16px; border-radius: 2px;
                   margin-bottom: 14px; }}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_app():
    """One Flask app (and DB engine) shared across reruns and sessions on this server.

    Rebuilding it on every Streamlit rerun would spin up a fresh SQLAlchemy
    connection pool every few seconds - st.cache_resource keeps a single
    instance alive for the life of the process instead.
    """
    return create_app()


def require_login() -> None:
    """Gate the dashboard behind the platform's existing username/password accounts.

    This is access control only - it decides who can *view* this dashboard,
    not which strategy they see. Every logged-in researcher currently sees
    the same single ThresholdStrategy account; per-researcher strategies
    are the multi-strategy framework this MVP deliberately doesn't build yet.
    """
    if "username" in st.session_state or st.user.is_logged_in:
        return

    st.title("LIVE STRATEGY DEMO")
    st.caption("Sign in with your platform account to view the live strategy")

    if st.button("Sign in with Google"):
        st.login()

    st.caption("— or use a platform account —")

    login_tab, register_tab = st.tabs(["Log In", "Register"])
    app = get_app()

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In")
        if submitted:
            with app.app_context():
                try:
                    AuthService().login(username=username, password=password)
                    st.session_state["username"] = username
                    st.rerun()
                except InvalidCredentialsError:
                    st.error("Invalid username or password.")

    with register_tab:
        with st.form("register_form"):
            reg_email = st.text_input("Email")
            reg_username = st.text_input("Username", key="reg_username")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            reg_submitted = st.form_submit_button("Create Account")
        if reg_submitted:
            with app.app_context():
                try:
                    AuthService().register(email=reg_email, username=reg_username, password=reg_password)
                    st.success("Account created — switch to the Log In tab.")
                except IntegrityError:
                    st.error("That email or username is already taken.")

    st.stop()


def strategy_input_placeholder() -> None:
    """Teaser for the not-yet-built feature: researchers submitting their own strategies.

    Deliberately inert (disabled controls) - this MVP runs one hardcoded
    strategy; this section only communicates the roadmap, it doesn't do
    anything yet.
    """
    st.subheader("Add Your Strategy")
    st.markdown(
        f'<div class="status-banner" style="background: rgba(255,165,0,0.08); '
        f'color: {COLOR_AMBER}; border-left: 3px solid {COLOR_AMBER};">COMING SOON — '
        f"self-service strategy submission for researchers</div>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.selectbox("Strategy type", ["ThresholdStrategy", "Custom (coming soon)"], disabled=True)
        c1, c2, c3 = st.columns(3)
        c1.number_input("Drop trigger %", value=0.5, disabled=True)
        c2.number_input("Rise trigger %", value=0.5, disabled=True)
        c3.number_input("Trade quantity", value=0.01, disabled=True)
        st.button("Submit Strategy", disabled=True)


def load_logs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the runner's CSV logs. Returns empty frames if it hasn't started yet."""
    if not os.path.exists(STATE_LOG_PATH):
        return pd.DataFrame(), pd.DataFrame()

    state = pd.read_csv(STATE_LOG_PATH, parse_dates=["timestamp"])
    trades = (
        pd.read_csv(TRADES_LOG_PATH, parse_dates=["timestamp"])
        if os.path.exists(TRADES_LOG_PATH)
        else pd.DataFrame()
    )
    return state, trades


def trade_stats(trades: pd.DataFrame) -> dict:
    """Total fills, completed round trips, and win rate across those round trips.

    ThresholdStrategy strictly alternates BUY/SELL per symbol (it never buys
    again while already holding), so pairing the Nth BUY with the Nth SELL
    is always correct - no need to match them by symbol/time.
    """
    if trades.empty:
        return {"total": 0, "round_trips": 0, "win_rate": None}

    buys = trades[trades["side"] == "BUY"]["fill_price"].reset_index(drop=True)
    sells = trades[trades["side"] == "SELL"]["fill_price"].reset_index(drop=True)
    completed = min(len(buys), len(sells))

    win_rate = None
    if completed:
        wins = (sells.iloc[:completed].values > buys.iloc[:completed].values).sum()
        win_rate = wins / completed * 100

    return {"total": len(trades), "round_trips": completed, "win_rate": win_rate}


def drawdown_stats(state: pd.DataFrame) -> dict:
    """Peak equity reached so far, and the largest drop from a peak (max drawdown)."""
    running_peak = state["equity"].cummax()
    drawdown = state["equity"] - running_peak
    return {"peak_equity": running_peak.iloc[-1], "max_drawdown": drawdown.min()}


def position_status(trades: pd.DataFrame, latest: pd.Series, trade_quantity: float | None) -> None:
    """Render a live IN POSITION / FLAT banner from the last trade's side. No emoji.

    Strictly alternating BUY/SELL means the last trade's side alone tells us
    whether the strategy is currently holding - no separate position lookup
    needed.
    """
    if trades.empty or trades.iloc[-1]["side"] == "SELL":
        st.markdown(
            f'<div class="status-banner" style="background: rgba(139,139,139,0.12); '
            f'color: {COLOR_MUTED}; border-left: 3px solid {COLOR_MUTED};">FLAT — watching for entry</div>',
            unsafe_allow_html=True,
        )
        return

    entry = trades.iloc[-1]
    qty = trade_quantity if trade_quantity is not None else entry["quantity"]
    unrealized = (latest["price"] - entry["fill_price"]) * qty
    st.markdown(
        f'<div class="status-banner" style="background: rgba(0,230,118,0.10); '
        f'color: {COLOR_GREEN}; border-left: 3px solid {COLOR_GREEN};">'
        f"IN POSITION — {qty} {entry['symbol']} @ ${entry['fill_price']:,.2f} "
        f"&nbsp;·&nbsp; UNREALIZED PNL: ${unrealized:,.2f}</div>",
        unsafe_allow_html=True,
    )


def terminal_layout(fig: go.Figure, height: int = 360) -> go.Figure:
    """Apply one consistent Bloomberg-terminal style to every chart on the page."""
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLOR_MUTED, size=12, family=MONO_FONT),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor=COLOR_GRID, zeroline=False, showline=True, linecolor=COLOR_GRID),
        yaxis=dict(gridcolor=COLOR_GRID, zeroline=False, showline=True, linecolor=COLOR_GRID),
        hovermode="x unified",
    )
    return fig


@st.fragment(run_every=REFRESH_SECONDS)
def live_view() -> None:
    state, trades = load_logs()

    if state.empty:
        st.info("Waiting for strategy_runner.py to write its first data point...")
        return

    latest = state.iloc[-1]
    starting_equity = state.iloc[0]["equity"]
    pnl = latest["equity"] - starting_equity
    pnl_pct = (pnl / starting_equity * 100) if starting_equity else 0

    position_status(trades, latest, trade_quantity=(trades.iloc[-1]["quantity"] if not trades.empty else None))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cash", f"${latest['cash']:,.2f}")
    col2.metric("Equity", f"${latest['equity']:,.2f}")
    col3.metric("PnL", f"${pnl:,.2f}", f"{pnl_pct:.2f}%")
    col4.metric(f"{latest['symbol']} Price", f"${latest['price']:,.2f}")

    stats = trade_stats(trades)
    dd = drawdown_stats(state)
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Total Fills", stats["total"])
    col6.metric("Round Trips", stats["round_trips"])
    col7.metric("Win Rate", f"{stats['win_rate']:.0f}%" if stats["win_rate"] is not None else "—")
    col8.metric("Max Drawdown", f"${dd['max_drawdown']:,.2f}")

    st.caption(f"Last updated {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC · refreshes every {REFRESH_SECONDS}s")

    left, right = st.columns(2)

    with left:
        st.subheader("Equity Curve")
        eq = go.Figure()
        eq.add_trace(go.Scatter(
            x=state["timestamp"], y=state["equity"], mode="lines", name="equity",
            line=dict(color=COLOR_CYAN, width=2),
            fill="tozeroy", fillcolor="rgba(34, 211, 238, 0.08)",
        ))
        eq.update_yaxes(range=[state["equity"].min() * 0.999, state["equity"].max() * 1.001])
        st.plotly_chart(terminal_layout(eq), width="stretch")

    with right:
        st.subheader(f"{latest['symbol']} Price")
        symbol_state = state[state["symbol"] == latest["symbol"]]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=symbol_state["timestamp"], y=symbol_state["price"],
            mode="lines", name="price", line=dict(color=COLOR_WHITE, width=1.5),
        ))

        if not trades.empty:
            symbol_trades = trades[trades["symbol"] == latest["symbol"]]
            buys = symbol_trades[symbol_trades["side"] == "BUY"]
            sells = symbol_trades[symbol_trades["side"] == "SELL"]
            fig.add_trace(go.Scatter(
                x=buys["timestamp"], y=buys["fill_price"], mode="markers", name="BUY",
                marker=dict(symbol="triangle-up", size=12, color=COLOR_GREEN,
                            line=dict(color="rgba(0,0,0,0.5)", width=1)),
            ))
            fig.add_trace(go.Scatter(
                x=sells["timestamp"], y=sells["fill_price"], mode="markers", name="SELL",
                marker=dict(symbol="triangle-down", size=12, color=COLOR_RED,
                            line=dict(color="rgba(0,0,0,0.5)", width=1)),
            ))

        st.plotly_chart(terminal_layout(fig), width="stretch")

    st.subheader("Trade Log")
    if trades.empty:
        st.caption("No trades yet.")
    else:
        st.dataframe(trades.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)


require_login()

header_left, header_right = st.columns([5, 1])
with header_left:
    st.title("LIVE STRATEGY DEMO")
    st.caption("ThresholdStrategy trading live Binance data through the real risk-checked order pipeline")
with header_right:
    display_name = st.session_state.get("username") or st.user.get("name") or st.user.get("email") or "researcher"
    st.caption(f"Signed in as {display_name}")
    if st.button("Log Out"):
        st.session_state.pop("username", None)
        if st.user.is_logged_in:
            st.logout()
        else:
            st.rerun()

live_view()
strategy_input_placeholder()
