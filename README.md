# Trading Platform

A distributed paper trading platform built across independently deployable services Python Flask API, a C++ gRPC risk engine, a Kafka event bus, a WebSocket price feed, and a React frontend. Simulates real exchange architecture with in-memory risk checks, live price simulation, and real-time browser updates.

## Architecture

```
Browser (React)
    ↕ WebSocket          ↕ HTTP/REST
         │                    │
WebSocket Service         Flask API
(price broadcast)         (orders, auth, portfolio)
         │                    │
         └──── Kafka ─────────┘
                │         │
         "prices"    "trade_filled"
                │         │
         C++ Risk Engine (gRPC :50051)
         ├── GBM price simulation thread
         ├── In-memory PriceStore (shared_mutex)
         ├── In-memory UserStateStore (per-user mutex)
         └── CheckOrder | UpdateState | LoadUser | GetPrice | GetAllPrices
                              │
                        PostgreSQL :5433
                        (users, orders, positions, ledger)
```

### Why C++

Order risk validation runs in a C++ inmemory engine rather than querying PostgreSQL on every order. This reduces CheckOrder latency from ~8ms (DB roundtrip) to ~180μs (RAM lookup) which is a 40x improvement. `shared_mutex` allows thousands of concurrent price reads while the GBM thread writes once per second.

### Why Kafka

After a trade fills, Flask publishes a `trade_filled` event to Kafka rather than calling the C++ engine synchronously. The C++ engine and WebSocket service consume independently, decoupling state synchronisation from the HTTP request lifecycle and making each service independently restartable.

### Why WebSockets

GBM produces price updates every second. Without WebSockets, 200 users would generate 200 HTTP polls per second. With WebSockets, one Kafka consumer broadcasts to all 200 connections simultaneously so that there are zero wasted requests.

---

## Services

| Service | Language | Port |
|---|---|---|
| Flask API | Python | 5000 |
| C++ Risk Engine | C++17 | 50051 (gRPC) |
| PostgreSQL | Docker | 5433 |
| Redpanda (Kafka) | Docker | 9092 |
| WebSocket Service | Python | 5001 |
| Prometheus | Docker | 9090 |
| Grafana | Docker | 3000 |
| React Frontend | Node.js | 3001 |

---

## Prerequisites

- Docker Desktop
- MSYS2 UCRT64 (for building C++)
- Python 3.11+
- Node.js 18+
- CMake 3.20+, Ninja

MSYS2 packages required:
```bash
pacman -S mingw-w64-ucrt-x86_64-cmake \
          mingw-w64-ucrt-x86_64-ninja \
          mingw-w64-ucrt-x86_64-grpc \
          mingw-w64-ucrt-x86_64-protobuf \
          mingw-w64-ucrt-x86_64-postgresql
```

---

## Running the Platform

### 1. Start infrastructure (PostgreSQL + Redpanda)

```bash
docker-compose up -d
```

### 2. Run database migrations

```bash
cd Trading-Platform
poetry install
poetry run flask db upgrade
```

### 3. Seed market data

```bash
docker exec -it trading-platform-postgres-1 psql -U trading_user -d trading_platform
```

```sql
INSERT INTO market_prices (symbol, price, volatility, drift, updated_at) VALUES
('AAPL', 182.50, 0.02, 0.0001, NOW()),
('MSFT', 415.00, 0.018, 0.0001, NOW()),
('TSLA', 245.00, 0.04, 0.0001, NOW()),
('GOOGL', 175.00, 0.022, 0.0001, NOW()),
('AMZN', 195.00, 0.025, 0.0001, NOW());
\q
```

### 4. Build the C++ risk engine (MSYS2 UCRT64)

```bash
cd risk_engine_cpp
mkdir -p build && cd build
cmake .. -G "Ninja"
ninja
```

### 5. Start the C++ risk engine (MSYS2 UCRT64)

```bash
./risk_engine.exe
```

Expected output:
```
Connected to PostgreSQL
Loaded 5 symbols into PriceStore
gRPC server listening on port 50051
```

### 6. Start the Flask API

```bash
cd Trading-Platform
poetry run flask run
```

### 7. Start the WebSocket service

```bash
poetry run python websocket_service.py
```

### 8. Start the React frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3001](http://localhost:3001)

---

## Monitoring

Prometheus scrapes metrics from both the Flask API and C++ risk engine every 15 seconds.

- Prometheus: [http://localhost:9090](http://localhost:9090)
- Grafana: [http://localhost:3000](http://localhost:3000) (admin / admin)

Key metrics tracked:
- `checkorder_latency_us` — CheckOrder duration in microseconds
- `orders_per_second` — order throughput
- `gbm_tick_rate` — GBM simulation frequency
- `flask_request_latency_seconds` — HTTP endpoint latency
- `grpc_call_latency_seconds` — Flask → C++ gRPC call duration

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login, returns JWT |
| POST | `/auth/refresh` | Refresh access token |

### Trading
| Method | Endpoint | Description |
|---|---|---|
| POST | `/orders` | Place buy/sell order |
| GET | `/orders` | Order history |
| GET | `/portfolio` | Current positions + cash |
| GET | `/portfolio/history` | P&L history |

### Market Data
| Method | Endpoint | Description |
|---|---|---|
| GET | `/prices` | All current prices |
| GET | `/prices/<symbol>` | Single symbol price |

---

## Project Structure

```
Trading-Platform/
├── app.py                      # Flask app factory
├── config.py                   # Environment config
├── docker-compose.yml          # PostgreSQL + Redpanda + Prometheus + Grafana
├── routes/
│   ├── auth_routes.py
│   ├── order_routes.py
│   ├── portfolio_routes.py
│   └── market_routes.py
├── services/
│   ├── auth_service.py
│   ├── order_service.py
│   ├── risk_engine_client.py   # gRPC client wrapping C++ calls
│   └── kafka_service.py        # Kafka producer/consumer
├── models/
│   ├── user.py
│   ├── account.py
│   ├── order.py
│   ├── position.py
│   ├── market_price.py
│   └── ledger_entry.py
├── websocket_service.py        # Kafka consumer → WebSocket broadcast
├── risk_engine_cpp/
│   ├── proto/trading.proto     # gRPC service contract
│   ├── src/
│   │   ├── main.cpp            # Entry point, DB seed, GBM thread, gRPC server
│   │   ├── price_store.hpp/cpp # Thread-safe in-memory price cache
│   │   ├── user_state_store.hpp/cpp  # Per-user cash + positions
│   │   └── trading_service.hpp/cpp   # gRPC RPC implementations
│   └── CMakeLists.txt
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Dashboard.tsx
    │   │   ├── Portfolio.tsx
    │   │   └── Trade.tsx
    │   └── components/
    │       ├── PriceBoard.tsx  # WebSocket live prices
    │       └── OrderForm.tsx
    └── package.json
```

---

## Environment Variables

Copy `.env.example` to `.env`:

```
FLASK_APP=app.py
FLASK_ENV=development
DATABASE_URL=postgresql://trading_user:trading_pass@localhost:5433/trading_platform
JWT_SECRET_KEY=your-secret-key
KAFKA_BROKER=localhost:9092
RISK_ENGINE_HOST=localhost:50051
```
