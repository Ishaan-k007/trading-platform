# Dashboard handoff

## Scope and ownership

The UI changes are confined to `streamlit_app.py`, `dashboard_ui.py`,
`dashboard_data.py`, and `tests/dashboard/`. Execution, strategy configuration,
protobuf definitions, database models, migrations, and Kafka workers are not changed.

Start the UI with the existing Python environment:

```powershell
poetry run streamlit run streamlit_app.py
```

The sign-in screen also offers **Open sample walkthrough**. This requires no
backend or credentials and exposes only locally generated illustrative data.
Authenticated users can choose Live session, Recorded session, or Sample walkthrough.
The live view remains a shared research demo of `STRATEGY_USERNAME`, not a personal
portfolio for the viewing user. Existing platform and optional Google sign-in remain.

## Features

- Market watch: five USDT pairs, bid, ask, spread, quote freshness, and up to 90
  observed points per sparkline. Change is over that observed window, not 24 hours.
- System pulse: engine reachability, database read availability, strategy-account
  persisted fill count and last-fill time, and median dashboard quote RPC latency.
  **This is not CheckOrder/ExecuteOrder latency and does not prove Kafka health.**
- Recorded-session playback: a snapshot of existing CSV files, with play/pause,
  restart, next fill, seek, and speed controls. Playback cannot submit orders.
- Sample walkthrough: deterministic illustrative prices and four scripted fills.
  It is visibly labelled as sample data, with backend health and execution latency
  explicitly not measured. It does not write the strategy CSV files or call services.
- Existing equity and price/fill charts retain the terminal palette. The trade
  summary now matches FIFO by symbol, including partial exits. Unknown currency
  and incomplete histories are displayed rather than treated as verified results.

## Read-only integration contract for backend work

1. gRPC `GetPrice(GetPriceRequest(symbol))` returns `symbol`, `price`, `best_bid`,
   `best_ask`, and ISO-8601 UTC `updated_at`. The dashboard calls the generated stub
   directly so changes to the execution client do not require UI changes. Each call
   has a 700ms deadline; the five calls run concurrently. Refresh is every 2 seconds.
   Quote age over 10 seconds is marked stale, and unparseable timestamps unverified.
   This display check does not replace engine-side stale-price rejection.
2. SQL reads use `users.username`, `accounts.user_id/currency`, and
   `orders.user_id/status/created_at`. The query counts only `FILLED` orders for the
   configured strategy account. Reads use a separate bounded connection pool and a
   short transaction; PostgreSQL statements time out after 1 second. Refresh is
   every 5 seconds. No INSERT/UPDATE/DELETE is issued by these adapters.
3. `strategy_state.csv`: required columns `timestamp,symbol,price,cash,equity`.
   Add **`currency`** to each row for correctly labelled recorded playback.
4. `strategy_trades.csv`: required columns `timestamp,side,symbol,quantity,fill_price`.
   Optional `order_id,client_order_id,event_id` are shown in the execution tape.
5. Timestamps should be UTC. The UI handles a writer's incomplete final CSV line
   and reports invalid complete rows. It displays runner-log staleness separately
   from engine quote freshness. Existing mixed-session logs are not recovery state.

Live portfolio totals are hidden when the database account currency is not USDT.
Recorded totals require a `currency=USDT` column; old files without currency metadata
are not silently re-labelled. This avoids masking the existing GBP/USDT backend bug.
Cash still shows its known units, and market prices remain visible.

## Configuration

Existing `.env` settings are read without being modified:

| Setting | Default / purpose |
| --- | --- |
| `RISK_ENGINE_HOST` / `RISK_ENGINE_PORT` | `localhost` / `50051` |
| `DATABASE_URL` | Existing SQLAlchemy database URL |
| `STRATEGY_USERNAME` | `strategy_bot`; account shown in health counts |
| `DASHBOARD_SYMBOLS` | BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT; maximum five USDT pairs |
| `DASHBOARD_LOG_DIR` | Project `logs/`; can point at a separate recorded session |
| `DATA_MODE` | `live`; label for the connected feed, e.g. `replay` for a backend replay feed |

## Backend replay is a separate integration

UI playback is not an end-to-end trading demonstration. For that, supply an isolated
replay feed, engine/account, and runner which generate real fills. Point this UI at
their gRPC endpoint, database, and log directory, set `DATA_MODE=replay`, and choose
Live session (the connected view). The UI never injects prices into a live engine,
lowers thresholds, launches a runner, or shares sample data with the backend.

## Verification

```powershell
poetry run pytest tests/dashboard -q -p no:cacheprovider
```

These tests cover CSV snapshots, invalid data, cross-symbol/partial-fill accounting,
sample consistency, missing services, credential-error redaction, and Streamlit
playback interactions. They do not claim to verify the trading engine or Kafka.
