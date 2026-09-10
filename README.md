# Trading Platform

A paper-trading platform built as a set of independently runnable services: a
Python Flask API, a C++ gRPC risk engine, a live Binance order-book feed, a
Kafka-based fill pipeline, an automated strategy runner, and a Streamlit
dashboard. It models real exchange plumbing — in-memory risk checks on the order
hot path, a write-ahead log for durability, and event-driven persistence —
against live market data.

## Architecture

```
                 Binance (live order-book WebSocket)
                          │  depth snapshots, ~100 symbols per connection
                          ▼
                 pipeline/orderbook_feed_producer.py
                          │  UpdateOrderBook (gRPC)
                          ▼
  strategy_runner.py   ┌──────────────────────────────┐        ┌────────────────┐
      │                │      C++ Risk Engine :50051   │        │   PostgreSQL   │
      │ place_order()  │                              │        │     :5433      │
      ▼                │  OrderBook      (per-symbol) │        │ users, orders, │
  Flask API :5000 ─────▶  PriceStore     (shared_mtx) │        │ positions,     │
  (auth, orders,   gRPC │  UserStateStore (per-user)  │        │ ledger         │
   portfolio,           │  WAL writer  ───────────┐   │        └────────▲───────┘
   market)              └─────────────────────────┼───┘                 │
      │                                           ▼                     │
      │                                        wal.log                  │
      ▼                                           │ pipeline/wal_producer.py
  Streamlit :8501                                 ▼                     │
  (equity curve,                        Kafka topic "order-fills"       │
   trades, live P&L)                              │ pipeline/fill_consumer.py
      ▲                                           └─────────────────────┘
      │ reads
  logs/strategy_*.csv  ◀── written by strategy_runner.py
```

### Why a C++ risk engine

Order risk checks — *does the user have the cash / the shares?* — run against
in-memory state in a C++ process instead of hitting PostgreSQL on every order.
`PriceStore` and `OrderBook` use `shared_mutex` so many order checks read prices
concurrently while the Binance feed updates them; `UserStateStore` uses one mutex
per user so different users' orders never block each other.

### Why a write-ahead log + Kafka

When an order fills, the engine appends it to `wal.log` (a write-ahead log) and
returns. A separate process (`wal_producer.py`) tails that file and publishes
each fill to the Kafka topic `order-fills`; `fill_consumer.py` reads that topic
and applies the fill to PostgreSQL. This keeps durable persistence off the
order's hot path and lets other consumers (analytics, notifications) read the
same fill stream without touching the engine.

### Why the Binance feed is sharded

One WebSocket connection can't carry every USDT trading pair, and putting them
all on one connection means a single dropped connection blacks out every symbol.
The feed splits symbols into shards of ~100, one connection (and one thread)
each, so a dropped connection only interrupts its own shard.

## Services

| Service | Language | Port | Start command |
|---|---|---|---|
| PostgreSQL | Docker | 5433 | `docker compose up -d` |
| Kafka | Docker | 9092 | `docker compose up -d` |
| C++ risk engine | C++17 | 50051 (gRPC) | `risk_engine_cpp/build/risk_engine.exe` |
| Binance order-book feed | Python | — | `python pipeline/orderbook_feed_producer.py` |
| WAL producer | Python | — | `python pipeline/wal_producer.py` |
| Fill consumer | Python | — | `python pipeline/fill_consumer.py` |
| Flask API | Python | 5000 | `flask run` |
| Strategy runner | Python | — | `python strategy_runner.py` |
| Streamlit dashboard | Python | 8501 | `streamlit run streamlit_app.py` |

Or start the whole stack with `scripts/run_all.sh` (see [Running](#running)).

## Prerequisites

- Docker Desktop
- Python 3.11+ and [Poetry](https://python-poetry.org/)
- MSYS2 UCRT64 with CMake, Ninja, gRPC, Protobuf and libpq — needed to build
  the C++ engine. The engine is not checked in; you build it once (below).

MSYS2 UCRT64 packages:

```bash
pacman -S mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja \
          mingw-w64-ucrt-x86_64-grpc mingw-w64-ucrt-x86_64-protobuf \
          mingw-w64-ucrt-x86_64-postgresql
```

## Setup

From a clean checkout, in an **MSYS2 UCRT64 shell**:

```bash
cp .env.example .env            # defaults match docker compose as-is
poetry install
docker compose up -d            # PostgreSQL + Kafka
poetry run flask db upgrade     # create tables from an empty database
bash scripts/build_engine.sh    # build the C++ risk engine
```

That's the whole build — no prebuilt binaries, no manual database steps. The
generated gRPC stubs (`services/trading_pb2*.py`, and the C++ stubs during the
engine build) are produced from `risk_engine_cpp/proto/trading.proto`; the
Python ones are checked in, so regenerate them with `bash scripts/gen_proto.sh`
only if you edit the proto. `scripts/run_all.sh` also runs `build_engine.sh`
itself the first time if the engine isn't built yet.

## Running

### Option A — one script (recommended)

Run from an **MSYS2 UCRT64 shell** — the C++ engine needs the UCRT64 runtime DLLs
on `PATH`, and only that shell provides them. The script locates Docker and the
Poetry virtualenv itself, so neither has to be on your `PATH`.

```bash
bash scripts/run_all.sh            # start everything, in dependency order
bash scripts/run_all.sh --fresh    # same, but wipe wal.log + strategy CSVs first
bash scripts/stop_all.sh           # stop everything, including the Docker containers
```

**Docker Desktop must already be running.** The script prints `1/8 … 8/8` and
waits for Postgres, the gRPC engine (`:50051`), and Flask (`:5000`) to actually
accept connections before continuing; it ends with `Up.` and the dashboard/API
URLs. Per-service output goes to `logs/<name>.out.log` and `logs/<name>.err.log`
— if a step reports `TIMEOUT`, read that service's `.err.log`.

### Option B — manually, in order

Each in its own terminal, from the repo root:

1. `docker compose up -d`
2. `risk_engine_cpp/build/risk_engine.exe` (MSYS2 UCRT64 shell) — wait for `gRPC server listening on port 50051`
3. `poetry run python pipeline/orderbook_feed_producer.py` — wait for `[shard 0] Connected`
4. `poetry run python pipeline/wal_producer.py`
5. `poetry run python pipeline/fill_consumer.py`
6. `poetry run flask run`
7. `poetry run python strategy_runner.py` — begins placing paper trades on `BTCUSDT`
8. `poetry run streamlit run streamlit_app.py`

Stop: `Ctrl-C` each terminal, then `docker compose stop`.

Run the engine from the repo root so its `wal.log` and `wal_producer.py` resolve
to the same file. The engine seeds `PriceStore` from `market_prices` on startup,
but the Binance feed supplies live prices for every USDT pair — you don't need to
seed `market_prices` unless you want non-crypto symbols.

## Using it

Once the stack is up:

1. **Open the dashboard** at <http://localhost:8501> and register / log in with a
   platform account (or Google).
2. **The strategy bot trades on its own.** `strategy_runner.py` polls BTCUSDT and
   fires a paper BUY when the price falls 0.5% below its reference, then a SELL
   when it recovers 0.5%. The first trade can take a while — follow
   `logs/strategy_runner.out.log`. The dashboard's equity curve and trade log
   fill in as it runs.
3. **Or place orders yourself** against the API:

   ```bash
   API=http://localhost:5000/api/v1

   curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
     -d '{"email":"me@test.local","username":"me","password":"password123"}'

   TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
     -d '{"username":"me","password":"password123"}' \
     | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

   curl -s -X POST $API/orders -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"order_id":"order-1","symbol":"BTCUSDT","side":"BUY","quantity":0.001,"order_type":"MARKET"}'

   curl -s $API/portfolio -H "Authorization: Bearer $TOKEN"
   curl -s $API/orders    -H "Authorization: Bearer $TOKEN"
   ```

   An order returns `FILLED` right away; it appears in PostgreSQL a moment later,
   once the WAL → Kafka → consumer chain has run (see
   [Known limitations](#known-limitations)).

## API

Base URL `http://localhost:5000/api/v1`. Trading and portfolio routes require a
JWT from `/auth/login`.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create an account (starts with 10,000 cash) |
| POST | `/auth/login` | Returns access + refresh tokens |
| POST | `/auth/refresh` | New access token from a refresh token |
| POST | `/orders` | Place a BUY/SELL, MARKET/LIMIT order |
| GET | `/orders` | Order history |
| GET | `/portfolio` | Cash + positions, marked to live prices |
| GET | `/market/prices` | All current prices |
| GET | `/market/prices/<symbol>` | One symbol's price |

`GET /metrics` (on the Flask app, no prefix) exposes Prometheus-format metrics —
currently `execute_order_latency_seconds`.

## Order flow

1. `POST /orders` → `OrderService.place_order` loads the user into the engine if
   needed, then makes a **single** `ExecuteOrder` call (gRPC).
2. Holding that user's lock for the whole operation, the engine validates the
   request, prices it from the order book, checks funds/position, computes the
   new balances, appends the fill to `wal.log`, applies the change to its
   in-memory state, and caches the result under the caller's `client_order_id`.
   The lock is never released mid-way, so concurrent orders for the same user
   cannot interleave and overwrite each other.
3. The engine returns a typed result (`FILLED`, `INSUFFICIENT_FUNDS`,
   `LIMIT_NOT_MET`, `IDEMPOTENCY_CONFLICT`, …). Python maps it to an HTTP
   response and computes no balances of its own.
4. The API responds `201 FILLED`.
5. Asynchronously: `wal_producer.py` → Kafka `order-fills` (keyed by `user_id`,
   so one user's fills stay ordered) → `fill_consumer.py` → PostgreSQL
   (`orders`, `accounts`, `positions`).

A retry carrying the same `client_order_id` replays the original outcome
instead of executing twice. See [docs/order-identifiers.md](docs/order-identifiers.md)
for what each identifier is and why it exists.

## Accounting rules

Accounts are denominated in **USDT** — the platform trades USDT-quoted pairs and
performs no FX conversion anywhere. All monetary and quantity columns are
`numeric(28, 8)`; scale 8 is the smallest unit Binance quotes. Values cross from
the engine's doubles into exact decimals at the persistence boundary, rounding
half-up. Short positions are not permitted: the engine rejects a SELL for more
than the account holds. The policy lives in one place, [core/money.py](core/money.py).

## Documentation

| Document | Covers |
|---|---|
| [docs/order-identifiers.md](docs/order-identifiers.md) | `client_order_id`, `order_id`, `event_id`, `account_sequence` — what each is, where it is minted, why four and not one |
| [docs/testing-execute-order.md](docs/testing-execute-order.md) | The testing strategy: why the race test cannot be a unit test, how the engine tests are made deterministic |
| [docs/hardening-roadmap.md](docs/hardening-roadmap.md) | Every known gap between this and a production system — the failure, why it is not covered, and how it would be fixed |

Each is also rendered as a PDF alongside its source.

## Known limitations

Summarised here; [docs/hardening-roadmap.md](docs/hardening-roadmap.md) has the
full list with failure modes and fixes.

- **Fill persistence is eventually consistent.** The API reports `FILLED` before
  the WAL → Kafka → consumer chain has written the fill to PostgreSQL, so
  `GET /portfolio` can briefly lag a just-placed order.
- **The engine's WAL write follows the state mutation** rather than preceding
  it, so a crash between the two loses that fill.
- **The double-entry ledger is not maintained per trade.** `ledger_entries`
  records only the opening deposit; `risk_checks`, `orders.rejection_reason` and
  `positions.realised_pnl` are defined but unpopulated — rejections never reach
  PostgreSQL at all, because only fills flow through the WAL.
- **Fills always execute at top of book.** Order size is ignored: no walking the
  book, no slippage, no fees, no partial fills.
- **One Kafka broker, one partition.** Fine for a single-node demo; not highly
  available.
- **GBM price simulation is disabled** (`run_gbm` in `main.cpp`) — pricing comes
  entirely from the live Binance order book.
