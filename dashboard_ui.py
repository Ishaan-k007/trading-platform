"""Read-only Streamlit presentation, independent of order-service changes."""

from datetime import datetime, timezone
from html import escape
import math
import os
from pathlib import Path
import statistics
import time

from dotenv import load_dotenv
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard_data import (
    DEFAULT_SYMBOLS,
    MarketReader,
    age_label,
    age_seconds,
    database_status,
    parse_symbols,
    read_log,
    sample_session,
    summarize_trades,
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
LOG_DIR = Path(os.getenv("DASHBOARD_LOG_DIR", str(ROOT / "logs")))
SYMBOLS = parse_symbols(os.getenv("DASHBOARD_SYMBOLS", ",".join(DEFAULT_SYMBOLS)))
AMBER, CYAN, GREEN, RED, MUTED = "#FFA500", "#22D3EE", "#00E676", "#FF5964", "#939AA4"
MODES = ("Live session", "Recorded session", "Sample walkthrough")
CSS = """
<style>
.stApp {background:#060809;color:#e8e8e8;font-family:Consolas,'Courier New',monospace}
.block-container {padding-top:1.5rem;padding-bottom:2rem;max-width:1600px}
h1,h2,h3 {font-family:Consolas,'Courier New',monospace!important}
h1 {color:#ffa500!important;font-size:1.9rem!important;letter-spacing:2px;margin-bottom:0!important}
h3 {font-size:.94rem!important;letter-spacing:1.3px;text-transform:uppercase;border-bottom:1px solid #302613;padding-bottom:.6rem!important}
[data-testid=stMetricLabel] {color:#939aa4;text-transform:uppercase;font-size:.72rem;letter-spacing:1px}
[data-testid=stMetricValue] {font-size:1.65rem;font-family:Consolas,monospace}
[data-testid=stMetric] {background:#0d1114;border:1px solid #252b30;padding:12px;border-radius:4px}
[data-testid=stCaptionContainer] {color:#939aa4}
.eyebrow {font-size:11px;letter-spacing:3px;color:#8a939d;margin-bottom:4px}
.section-label {font-size:11px;color:#939aa4;letter-spacing:2px;text-transform:uppercase;margin:18px 0 10px}
.market-grid {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.market-card {background:linear-gradient(135deg,#101619,#0a0e10);border:1px solid #263038;border-radius:5px;padding:14px 15px 9px;min-width:0}
.market-head {display:flex;justify-content:space-between;gap:5px;font-size:12px;letter-spacing:1px;font-weight:bold}
.market-price {font-size:25px;color:#eef1f4;margin:12px 0 3px;letter-spacing:-.6px}
.market-change {font-size:10px;min-height:15px}
.quote-grid {display:grid;grid-template-columns:1fr 1fr;gap:5px;border-top:1px solid #253038;padding-top:8px;font-size:10px}
.quote-grid small {display:block;color:#83909a;font-size:9px;margin-bottom:2px;letter-spacing:1px}
.quote-footer {font-size:9px;color:#929ba3;margin-top:9px;display:flex;justify-content:space-between;gap:4px}
.health-grid {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:18px}
.health-card {border:1px solid #252b30;border-radius:4px;background:#0d1114;padding:12px}
.health-label {font-size:9px;letter-spacing:1.1px;color:#939aa4;text-transform:uppercase}
.health-value {font-size:15px;margin-top:8px;font-weight:bold}
.health-detail {font-size:9px;color:#929ba3;line-height:1.4;margin-top:5px}
.mode-banner {padding:11px 14px;border:1px solid #4c3716;border-left:3px solid #ffa500;background:#17130c;font-size:11px;line-height:1.65;margin:8px 0 14px}
.mode-banner strong {letter-spacing:1px;color:#ffc263}
.position-banner {padding:12px 14px;border:1px solid #25343a;border-left:3px solid #22d3ee;background:#0c161b;font-size:12px;margin-bottom:15px}
@media(max-width:1000px){.market-grid,.health-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:600px){.market-grid,.health-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.market-price{font-size:20px}.block-container{padding-left:1rem;padding-right:1rem}}
</style>
"""


def money(value, decimals=2):
    return (
        "—"
        if value is None or not math.isfinite(float(value))
        else f"{value:,.{decimals}f}"
    )


def price_text(value):
    return money(value, 5 if value is not None and 0 < value < 10 else 2)


@st.cache_resource
def get_app():
    from app import create_app

    return create_app()


@st.cache_resource
def get_market_reader():
    return MarketReader(
        os.getenv("RISK_ENGINE_HOST", "localhost"),
        int(os.getenv("RISK_ENGINE_PORT", "50051")),
    )


@st.cache_data(ttl=1.5, show_spinner=False)
def live_quotes():
    try:
        return get_market_reader().quotes(SYMBOLS)
    except Exception:
        return [
            {"symbol": s, "reachable": False, "error": "Unavailable"} for s in SYMBOLS
        ]


@st.cache_resource
def get_read_engine():
    from sqlalchemy import create_engine

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Database not configured")
    kwargs = (
        {"connect_args": {"connect_timeout": 1}} if url.startswith("postgresql") else {}
    )
    return create_engine(
        url, pool_pre_ping=True, pool_size=2, max_overflow=0, pool_timeout=1, **kwargs
    )


@st.cache_data(ttl=5, show_spinner=False)
def live_database_status():
    try:
        return database_status(
            get_read_engine(), os.getenv("STRATEGY_USERNAME", "strategy_bot")
        )
    except Exception:
        return {
            "online": False,
            "fills": None,
            "last_fill": None,
            "currency": None,
            "account_found": False,
        }


def signed_in():
    try:
        return bool(st.session_state.get("username") or st.user.is_logged_in)
    except Exception:
        return bool(st.session_state.get("username"))


def require_login():
    if signed_in():
        return True
    if st.session_state.get("sample_preview"):
        return False
    st.markdown(
        '<div class="eyebrow">PAPER TRADING / RESEARCH WORKSPACE</div>',
        unsafe_allow_html=True,
    )
    st.title("TRADING TERMINAL")
    st.caption("Live market data. Traceable paper fills. A strategy you can inspect.")
    st.markdown(
        '<div class="mode-banner"><strong>TAKE A LOOK AROUND</strong><br>Explore a scripted sample session without connecting to an account. Sample prices and fills are clearly labelled.</div>',
        unsafe_allow_html=True,
    )
    if st.button("Open sample walkthrough", type="primary", key="open_sample"):
        st.session_state.sample_preview = True
        st.rerun()
    st.divider()
    st.subheader("Sign in to your platform")
    try:
        has_google = "auth" in st.secrets
    except (FileNotFoundError, KeyError):
        has_google = False
    if has_google and st.button("Sign in with Google"):
        st.login()
    login, register = st.tabs(["Log in", "Create account"])
    with login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Log in", type="primary")
        if submit:
            try:
                from services.auth_service import AuthService

                with get_app().app_context():
                    AuthService().login(username=username, password=password)
                st.session_state.username = username
                st.rerun()
            except Exception as exc:
                st.error(
                    "Invalid username or password."
                    if type(exc).__name__ == "InvalidCredentialsError"
                    else "Sign-in service unavailable. Try again when the backend is ready."
                )
    with register:
        with st.form("register_form"):
            email = st.text_input("Email", key="register_email")
            username = st.text_input("Username", key="register_username")
            password = st.text_input(
                "Password", type="password", key="register_password"
            )
            submit = st.form_submit_button("Create account")
        if submit:
            if "@" not in email or len(username.strip()) < 3 or len(password) < 6:
                st.error(
                    "Use a valid email, a username of at least 3 characters, and a password of at least 6 characters."
                )
            else:
                try:
                    from services.auth_service import AuthService

                    with get_app().app_context():
                        AuthService().register(
                            email=email, username=username.strip(), password=password
                        )
                    st.success("Account created. You can now log in.")
                except Exception as exc:
                    st.error(
                        "Email or username already taken."
                        if type(exc).__name__ == "IntegrityError"
                        else "Registration unavailable. Please try again later."
                    )
    st.stop()


def sparkline(values, color):
    if len(values) < 2:
        return '<div style="height:41px;color:#64717b;font-size:9px;padding-top:15px">Collecting observations…</div>'
    lo, hi = min(values), max(values)
    span = hi - lo or max(abs(hi) * 0.0001, 0.0001)
    points = " ".join(
        f"{i * 200 / (len(values)-1):.1f},{34 - (v-lo) / span * 28:.1f}"
        for i, v in enumerate(values)
    )
    return f'<svg viewBox="0 0 200 42" width="100%" height="42" role="img" aria-label="Price observations"><polyline fill="none" stroke="{color}" stroke-width="1.8" points="{points}"/></svg>'


def render_market(quotes, histories, mode, clock):
    st.markdown(
        '<div class="section-label">Market watch · prices in USDT</div>',
        unsafe_allow_html=True,
    )
    cards = []
    for quote in quotes:
        symbol, error = quote["symbol"], quote.get("error")
        values = histories.get(symbol, [])
        age = age_seconds(quote.get("updated_at"), clock)
        if mode != MODES[0]:
            status, color = ("SAMPLE" if mode == MODES[2] else "RECORDED"), AMBER
        else:
            status, color = (
                ("LIVE", GREEN)
                if age is not None and age <= 10
                else ("STALE" if age is not None else "UNVERIFIED", AMBER)
            )
        if error:
            status, color = error.upper(), MUTED
        price = quote.get("price") if not error else None
        change = (
            (values[-1] / values[0] - 1) * 100
            if len(values) > 1 and values[0]
            else None
        )
        movement = GREEN if change is not None and change >= 0 else RED
        delta = (
            f"{change:+.3f}% · observed window"
            if change is not None
            else "No change history yet"
        )
        bid, ask = quote.get("best_bid"), quote.get("best_ask")
        spread = ask - bid if bid is not None and ask is not None else None
        cards.append(
            f"""<div class="market-card"><div class="market-head"><span>{escape(symbol)}</span><span style="color:{color};font-size:8px">● {escape(status)}</span></div>
            <div class="market-price">{price_text(price)}</div><div class="market-change" style="color:{movement if change is not None else MUTED}">{delta}</div>
            {sparkline(values, CYAN if mode == MODES[0] else AMBER)}
            <div class="quote-grid"><div><small>BID</small>{price_text(bid)}</div><div><small>ASK</small>{price_text(ask)}</div></div>
            <div class="quote-footer"><span>SPR {price_text(spread)}</span><span>{escape(age_label(age) if mode == MODES[0] else 'Playback time')}</span></div></div>"""
        )
    st.markdown(
        '<div class="market-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True
    )


def render_health(mode, quotes, status, trades, clock):
    st.markdown('<div class="section-label">System pulse</div>', unsafe_allow_html=True)
    if mode == MODES[0]:
        online = any(q.get("reachable") for q in quotes)
        samples = st.session_state.setdefault("quote_latencies", [])
        seen = st.session_state.setdefault("latency_sample_ids", {})
        for quote in quotes:
            sample_id = quote.get("sample_id")
            if sample_id is not None and seen.get(quote["symbol"]) != sample_id:
                if quote.get("latency_ms") is not None:
                    samples.append(quote["latency_ms"])
                seen[quote["symbol"]] = sample_id
        st.session_state.quote_latencies = samples[-120:]
        latency = statistics.median(samples[-120:]) if samples else None
        items = [
            (
                "Execution engine",
                "REACHABLE" if online else "UNAVAILABLE",
                "Read-only quote RPC",
                GREEN if online else RED,
            ),
            (
                "PostgreSQL",
                "CONNECTED" if status["online"] else "UNAVAILABLE",
                "Read-only account query",
                GREEN if status["online"] else RED,
            ),
            (
                "Persisted fills",
                str(status["fills"]) if status["fills"] is not None else "—",
                "Strategy account · database",
                CYAN,
            ),
            (
                "Quote RPC p50",
                f"{latency:.2f} ms" if latency is not None else "—",
                f"{min(len(samples),120)} recent successful requests",
                CYAN,
            ),
            (
                "Last persisted fill",
                age_label(age_seconds(status.get("last_fill"), clock)),
                "Strategy account · database",
                AMBER,
            ),
        ]
    else:
        last = trades.iloc[-1]["timestamp"] if not trades.empty else None
        items = [
            (
                "Execution engine",
                "NOT QUERIED",
                "Playback does not submit orders",
                MUTED,
            ),
            ("PostgreSQL", "NOT QUERIED", "No account data changed", MUTED),
            (
                "Visible fills",
                str(len(trades)),
                "Sample fills" if mode == MODES[2] else "Recorded fills",
                AMBER,
            ),
            ("Execution latency", "NOT MEASURED", "Playback is not a benchmark", MUTED),
            (
                "Last visible fill",
                age_label(age_seconds(last, clock)),
                "Relative to playback clock",
                AMBER,
            ),
        ]
    cards = [
        f'<div class="health-card"><div class="health-label">{escape(label)}</div><div class="health-value" style="color:{color}">{escape(value)}</div><div class="health-detail">{escape(detail)}</div></div>'
        for label, value, detail, color in items
    ]
    st.markdown(
        '<div class="health-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True
    )
    if mode == MODES[0]:
        st.caption(
            "Quote RPC p50 measures dashboard → engine round trips, not order-execution latency. Persisted fills can lag the strategy log; Kafka health is not inferred from these checks."
        )


def reset_playback():
    for key in (
        "replay_frame",
        "replay_base",
        "replay_anchor",
        "replay_playing",
        "recorded_snapshot",
    ):
        st.session_state.pop(key, None)


def seek_playback(frame=None):
    frame = st.session_state.get("replay_frame", 0) if frame is None else frame
    st.session_state.replay_frame = int(frame)
    st.session_state.replay_base = int(frame)
    st.session_state.replay_anchor = time.monotonic()


def toggle_playback():
    seek_playback()
    st.session_state.replay_playing = not st.session_state.get("replay_playing", False)


def playback_controls(state, trades):
    times = pd.Index(state["timestamp"].drop_duplicates())
    total = len(times)
    st.session_state.setdefault("replay_frame", min(16, total - 1))
    st.session_state.setdefault("replay_base", st.session_state.replay_frame)
    st.session_state.setdefault("replay_anchor", time.monotonic())
    st.session_state.setdefault("replay_playing", False)
    frame = st.session_state.replay_frame
    if st.session_state.replay_playing:
        frame = min(
            total - 1,
            st.session_state.replay_base
            + int(
                (time.monotonic() - st.session_state.replay_anchor)
                / 2
                * st.session_state.get("replay_speed", 2)
            ),
        )
    st.session_state.replay_frame = frame
    if frame == total - 1:
        st.session_state.replay_playing = False
    following = (
        trades[trades["timestamp"] > times[frame]] if not trades.empty else trades
    )
    next_frame = (
        int(times.searchsorted(following.iloc[0]["timestamp"]))
        if not following.empty
        else total - 1
    )
    play, restart, jump, speed = st.columns([1, 1, 1, 2])
    play.button(
        "Pause" if st.session_state.replay_playing else "Play",
        key="play_pause",
        on_click=toggle_playback,
        type="primary",
        width="stretch",
    )
    restart.button(
        "Restart",
        key="restart_replay",
        on_click=seek_playback,
        args=(0,),
        width="stretch",
    )
    jump.button(
        "Next fill",
        key="next_fill",
        on_click=seek_playback,
        args=(min(next_frame, total - 1),),
        disabled=following.empty,
        width="stretch",
    )
    speed.select_slider(
        "Playback speed",
        options=[1, 2, 4, 8],
        key="replay_speed",
        value=2,
        format_func=lambda x: f"{x}×",
        on_change=seek_playback,
    )
    if total > 1:
        st.slider(
            "Session position",
            0,
            total - 1,
            key="replay_frame",
            on_change=seek_playback,
        )
    st.caption(
        f"Frame {frame+1} / {total} · {times[frame].strftime('%Y-%m-%d %H:%M:%S')} UTC · seek and replay without placing orders"
    )
    return times[frame]


def chart_layout(fig):
    fig.update_layout(
        height=310,
        margin=dict(l=0, r=8, t=12, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, size=11, family="Consolas,monospace"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        xaxis=dict(gridcolor="rgba(255,165,0,.10)", zeroline=False),
        yaxis=dict(gridcolor="rgba(255,165,0,.10)", zeroline=False),
        hovermode="x unified",
    )
    return fig


def render_portfolio(state, trades, currency, mode):
    if state.empty:
        st.info(
            "Waiting for strategy observations. Market watch and system health remain available above."
        )
        st.caption(
            "Use Sample walkthrough to explore the charts, or Recorded session to play back an existing run."
        )
        return
    symbol = st.selectbox(
        "Chart instrument", state.symbol.unique().tolist(), key=f"chart_symbol_{mode}"
    )
    symbol_state = state[state.symbol == symbol]
    latest = state.iloc[-1]
    totals_valid = currency == "USDT"
    if not totals_valid:
        st.warning(
            f"Account currency is {currency or 'not recorded'}. Prices are quoted in USDT; combined equity and P&L are hidden until the units are verified. Cash is shown in its recorded account units."
        )
    stats = summarize_trades(trades)
    position = stats["positions"].get(symbol)
    if stats["incomplete"]:
        label = "INCOMPLETE TRADE HISTORY · holdings cannot be reconstructed reliably"
    elif position:
        label = f"{symbol} · {position['quantity']:g} held · average entry {price_text(position['average_price'])} USDT"
    else:
        label = f"{symbol} · FLAT IN VISIBLE FILL HISTORY · watching for an entry"
    st.markdown(
        f'<div class="position-banner">{escape(label)}</div>', unsafe_allow_html=True
    )
    first_equity = state.iloc[0].equity
    pnl = latest.equity - first_equity
    delta = f"{pnl/first_equity*100:+.3f}%" if first_equity and totals_valid else None
    cols = st.columns(4)
    cols[0].metric(f"Cash · {currency or 'units'}", money(latest.cash))
    cols[1].metric("Equity · USDT", money(latest.equity) if totals_valid else "—")
    cols[2].metric("Session P&L · USDT", money(pnl) if totals_valid else "—", delta)
    cols[3].metric(f"{symbol} · USDT", price_text(symbol_state.iloc[-1].price))
    left, right = st.columns(2)
    with left:
        st.subheader("Equity curve")
        if totals_valid:
            rows = state.drop_duplicates("timestamp", keep="last").tail(1200)
            fig = go.Figure(
                go.Scatter(
                    x=rows.timestamp,
                    y=rows.equity,
                    mode="lines",
                    name="Equity",
                    line=dict(color=CYAN, width=2),
                    fill="tozeroy",
                    fillcolor="rgba(34,211,238,.07)",
                )
            )
            lo, hi = rows.equity.min(), rows.equity.max()
            padding = max((hi - lo) * 0.2, abs(hi) * 0.0003, 0.1)
            fig.update_yaxes(range=[lo - padding, hi + padding])
            st.plotly_chart(chart_layout(fig), width="stretch", key="equity_chart")
        else:
            st.info("Equity chart paused until account and price currencies agree.")
    with right:
        st.subheader(f"{symbol} · price & fills")
        rows = symbol_state.tail(1200)
        fig = go.Figure(
            go.Scatter(
                x=rows.timestamp,
                y=rows.price,
                mode="lines",
                name="Midpoint",
                line=dict(color=AMBER, width=1.7),
            )
        )
        for side, color, marker in [
            ("BUY", GREEN, "triangle-up"),
            ("SELL", RED, "triangle-down"),
        ]:
            selected = trades[
                (trades.symbol == symbol)
                & (trades.side == side)
                & (trades.timestamp >= rows.timestamp.min())
            ]
            fig.add_trace(
                go.Scatter(
                    x=selected.timestamp,
                    y=selected.fill_price,
                    mode="markers",
                    name=side,
                    marker=dict(
                        symbol=marker,
                        size=12,
                        color=color,
                        line=dict(color="#080c0f", width=1),
                    ),
                )
            )
        st.plotly_chart(chart_layout(fig), width="stretch", key="price_chart")
    cols = st.columns(4)
    cols[0].metric("Visible fills", stats["fills"])
    cols[1].metric("Matched exits", stats["exits"])
    cols[2].metric(
        "Winning exits",
        f"{stats['win_rate']:.0f}%" if stats["win_rate"] is not None else "—",
    )
    cols[3].metric(
        "Max drawdown · USDT",
        money((state.equity - state.equity.cummax()).min()) if totals_valid else "—",
    )
    st.caption(
        "Position estimates use visible fills, matched FIFO per instrument. Winning exits exclude fees; this is not a performance forecast. Portfolio observations can lag fills."
    )
    st.subheader("Sample execution tape" if mode == MODES[2] else "Execution tape")
    if trades.empty:
        st.caption(
            "No fills in this part of the session. In playback, use Next fill to advance."
        )
    else:
        columns = [
            c
            for c in (
                "timestamp",
                "symbol",
                "side",
                "quantity",
                "fill_price",
                "order_id",
                "client_order_id",
                "event_id",
            )
            if c in trades.columns
        ]
        st.dataframe(
            trades[columns].sort_values("timestamp", ascending=False).head(200),
            hide_index=True,
            width="stretch",
        )


@st.fragment(run_every=2)
def terminal_view(mode):
    now = datetime.now(timezone.utc)
    warnings = []
    if mode == MODES[2]:
        state, trades, market = sample_session()
        st.markdown(
            '<div class="mode-banner"><strong>SAMPLE WALKTHROUGH · NOT LIVE TRADING</strong><br>Scripted prices and illustrative zero-fee fills. No orders are sent, no account is changed, and backend health is not simulated.</div>',
            unsafe_allow_html=True,
        )
    else:
        if mode == MODES[1] and "recorded_snapshot" in st.session_state:
            state, trades, warnings = st.session_state.recorded_snapshot
        else:
            state, first = read_log(LOG_DIR / "strategy_state.csv", "state")
            trades, second = read_log(LOG_DIR / "strategy_trades.csv", "trades")
            warnings = first + second
            if mode == MODES[1]:
                st.session_state.recorded_snapshot = (state, trades, warnings)
        market = None
    for warning in warnings:
        st.warning(warning)
    status, currency = {"online": False, "currency": None}, None
    if mode != MODES[0]:
        if state.empty:
            st.info(
                "No recorded session is available yet. Select Sample walkthrough for a self-contained demonstration."
            )
            return
        if mode == MODES[1]:
            st.markdown(
                '<div class="mode-banner"><strong>RECORDED SESSION · PLAYBACK ONLY</strong><br>Snapshot of the existing strategy CSV logs. This replays observations and recorded fills; it does not execute trades again.</div>',
                unsafe_allow_html=True,
            )
        clock = playback_controls(state, trades)
        state, trades = (
            state[state.timestamp <= clock],
            trades[trades.timestamp <= clock],
        )
        currency = (
            str(state.iloc[-1]["currency"]) if "currency" in state.columns else None
        )
        source = market[market.timestamp <= clock] if market is not None else state
        histories, quotes = {}, []
        for symbol in DEFAULT_SYMBOLS:
            rows = source[source.symbol == symbol].tail(90)
            if rows.empty:
                quotes.append({"symbol": symbol, "error": "Not recorded"})
            else:
                row = rows.iloc[-1]
                quotes.append(
                    {
                        "symbol": symbol,
                        "price": row.price,
                        "best_bid": row.get("best_bid"),
                        "best_ask": row.get("best_ask"),
                        "updated_at": row.timestamp,
                    }
                )
                histories[symbol] = rows.price.tolist()
    else:
        clock, quotes, status = now, live_quotes(), live_database_status()
        currency = status.get("currency")
        stored = st.session_state.setdefault("market_history", {})
        for quote in quotes:
            if quote.get("error"):
                continue
            entries = stored.setdefault(quote["symbol"], [])
            if not entries or entries[-1][0] != quote.get("updated_at"):
                entries.append((quote.get("updated_at"), quote["price"]))
            stored[quote["symbol"]] = entries[-90:]
        histories = {s: [p for _, p in entries] for s, entries in stored.items()}
        st.caption(
            f"CONNECTED SESSION · {os.getenv('DATA_MODE','live').upper()} DATA · refreshed {now.strftime('%H:%M:%S')} UTC · quotes every 2s, database every 5s"
        )
    render_market(quotes, histories, mode, clock)
    render_health(mode, quotes, status, trades, clock)
    if mode == MODES[0] and not state.empty:
        age = age_seconds(state.iloc[-1].timestamp, now)
        if age is None or age > 15:
            st.warning(
                f"Strategy observations are stale ({age_label(age)}). Charts show the last recorded session, not a currently progressing run."
            )
        else:
            st.caption(
                f"Latest strategy observation: {age_label(age)} · shared strategy account {os.getenv('STRATEGY_USERNAME','strategy_bot')}"
            )
    render_portfolio(state, trades, currency, mode)


def main():
    st.set_page_config(page_title="Trading Terminal", page_icon="📈", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    authenticated = require_login()
    left, right = st.columns([4, 1])
    with left:
        st.markdown(
            '<div class="eyebrow">RESEARCH / EXECUTION / OBSERVABILITY</div>',
            unsafe_allow_html=True,
        )
        st.title("TRADING TERMINAL")
        st.caption("Python strategy → C++ risk engine → fill log → Kafka → PostgreSQL")
    with right:
        st.caption(
            f"Signed in as {st.session_state.get('username','researcher')}"
            if authenticated
            else "READ-ONLY SAMPLE"
        )
        if st.button(
            "Log out" if authenticated else "Back to sign in", key="leave_dashboard"
        ):
            st.session_state.clear()
            if authenticated:
                try:
                    if st.user.is_logged_in:
                        st.logout()
                except Exception:
                    pass
            st.rerun()
    if authenticated:
        mode = st.radio(
            "Session source",
            MODES,
            horizontal=True,
            key="dashboard_mode",
            on_change=reset_playback,
        )
        st.caption(
            "Shared strategy demonstration. These charts are not the signed-in user's personal portfolio."
        )
    else:
        mode = MODES[2]
    terminal_view(mode)
    with st.expander("About this workspace"):
        st.write(
            "This dashboard is read-only. Live mode observes the engine and the configured strategy account. Recorded mode snapshots CSV logs. The sample walkthrough is illustrative and works without a backend."
        )
        st.write(
            "To demo actual end-to-end execution, use an isolated replay feed and strategy runner supplied by the backend. This UI does not alter thresholds, inject prices, or place orders."
        )
        st.caption(
            "Strategy uploads and manual trading are outside this dashboard update."
        )
