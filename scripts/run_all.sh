#!/usr/bin/env bash
#
# Start the whole stack in dependency order.
#
# Run from an MSYS2 UCRT64 shell — the C++ engine needs the UCRT64 runtime
# DLLs on PATH.
#
#   bash scripts/run_all.sh           start everything
#   bash scripts/run_all.sh --fresh   wipe wal.log + strategy CSVs first
#
# Per-service output goes to logs/<name>.out.log / .err.log, PIDs to
# logs/<name>.pid. Stop everything with scripts/stop_all.sh.
#
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
mkdir -p logs

# The MSYS2 shell often runs with a minimal PATH that omits Docker Desktop even
# when it's on the Windows PATH. Add its standard location if `docker` is missing.
if ! command -v docker >/dev/null 2>&1; then
  for d in "/c/Program Files/Docker/Docker/resources/bin" \
           "${PROGRAMFILES:-/c/Program Files}/Docker/Docker/resources/bin"; do
    d="$(cygpath -u "$d" 2>/dev/null || echo "$d")"
    [[ -x "$d/docker.exe" ]] && { PATH="$PATH:$d"; export PATH; break; }
  done
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Is Docker Desktop installed and running?"
  exit 1
fi

if [[ "${1:-}" == "--fresh" ]]; then
  echo "Wiping wal.log, wal.cursor and strategy CSVs..."
  rm -f wal.log wal.cursor logs/strategy_state.csv logs/strategy_trades.csv
fi

# Use the venv's executables directly so recorded PIDs are the real processes
# (not a "poetry run" wrapper that stop_all.sh can't follow). Poetry isn't
# always on PATH — especially inside the MSYS2 shell — so fall back to its
# default cache location if the `poetry` command isn't there.
find_venv() {
  if command -v poetry >/dev/null 2>&1; then
    local p; p="$(poetry env info -p 2>/dev/null || true)"
    [[ -n "$p" && -d "$p" ]] && { echo "$p"; return 0; }
  fi
  local base
  for base in "${LOCALAPPDATA:-}" "$HOME/AppData/Local"; do
    [[ -n "$base" ]] || continue
    base="$(cygpath -u "$base" 2>/dev/null || echo "$base")"
    local m; m="$(ls -d "$base"/pypoetry/Cache/virtualenvs/trading-platform-* 2>/dev/null | head -1 || true)"
    [[ -n "$m" && -d "$m" ]] && { echo "$m"; return 0; }
  done
  return 1
}

VENV="$(find_venv)" || {
  echo "Could not find the project virtualenv. Run 'poetry install' first."
  exit 1
}
if [[ -d "$VENV/Scripts" ]]; then
  PATH="$VENV/Scripts:$PATH"     # Windows-layout venv (yours)
else
  PATH="$VENV/bin:$PATH"
fi
export PATH
export PYTHONUNBUFFERED=1        # so logs/*.log update live instead of in 8KB chunks
echo "  using venv: $VENV"

win_alive() {   # win_alive <windows-pid>
  tasklist //FI "PID eq $1" //NH 2>/dev/null | grep -qiE '\.exe'
}

start() {   # start <name> <command...>
  local name="$1"; shift
  if [[ -f "logs/$name.pid" ]] && win_alive "$(cat "logs/$name.pid")"; then
    echo "  $name already running (pid $(cat "logs/$name.pid")) — run stop_all.sh first"
    return
  fi
  "$@" > "logs/$name.out.log" 2> "logs/$name.err.log" &
  local mpid=$!
  sleep 0.3
  # Record the *Windows* PID: an MSYS2 job PID goes stale once it exec's into a
  # native .exe, so stop_all.sh keys off winpid via taskkill instead.
  local wpid
  wpid="$(cat "/proc/$mpid/winpid" 2>/dev/null || echo "$mpid")"
  echo "$wpid" > "logs/$name.pid"
  echo "  started $name (pid $wpid)"
}

wait_for() {   # wait_for <description> <command...>
  local desc="$1"; shift
  printf '  waiting for %s' "$desc"
  for _ in $(seq 1 60); do
    if "$@" >/dev/null 2>&1; then echo " ok"; return 0; fi
    printf '.'; sleep 1
  done
  echo " TIMEOUT"
  return 1
}

port_open() { (exec 3<>"/dev/tcp/localhost/$1") 2>/dev/null; }

echo "1/8  infrastructure (Postgres + Kafka)"
docker compose up -d
wait_for "Postgres" docker compose exec -T postgres pg_isready -U trading_user -q

echo "2/8  database migrations"
flask db upgrade

echo "3/8  C++ risk engine"
ENGINE="$ROOT/risk_engine_cpp/build/risk_engine.exe"
if [[ ! -x "$ENGINE" ]]; then
  echo "  engine not built yet - running scripts/build_engine.sh"
  bash "$ROOT/scripts/build_engine.sh"
fi
start risk_engine "$ENGINE"
wait_for "gRPC :50051" port_open 50051

echo "4/8  Binance order-book feed"
start orderbook_feed python pipeline/orderbook_feed_producer.py

echo "5/8  WAL producer"
start wal_producer python pipeline/wal_producer.py

echo "6/8  fill consumer"
start fill_consumer python pipeline/fill_consumer.py

echo "7/8  Flask API"
start flask flask run
wait_for "Flask :5000" port_open 5000

echo "8/8  strategy runner + dashboard"
start strategy_runner python strategy_runner.py
start streamlit streamlit run streamlit_app.py --server.headless true

echo
echo "Up.  Dashboard: http://localhost:8501    API: http://localhost:5000/api/v1"
echo "Logs: logs/<name>.out.log / .err.log     Stop: bash scripts/stop_all.sh"
