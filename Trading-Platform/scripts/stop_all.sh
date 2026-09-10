#!/usr/bin/env bash
#
# Stop everything scripts/run_all.sh started, then stop the Docker
# infrastructure. Leaves Docker volumes (and your data) intact.
#
set -uo pipefail

cd "$(dirname "$0")/.."

# Primary path: taskkill each recorded Windows PID (//T also kills child
# processes, e.g. the Flask debug reloader's worker).
for pidfile in logs/*.pid; do
  [[ -e "$pidfile" ]] || continue
  name="$(basename "$pidfile" .pid)"
  wpid="$(cat "$pidfile")"
  if taskkill //F //T //PID "$wpid" >/dev/null 2>&1; then
    echo "stopped $name (pid $wpid)"
  fi
  rm -f "$pidfile"
done

# Backstop: catch anything the PID files missed, matched by command line.
powershell -NoProfile -Command "
  Get-CimInstance Win32_Process |
    Where-Object { \$_.CommandLine -match 'orderbook_feed_producer|wal_producer|fill_consumer|strategy_runner|streamlit_app' } |
    ForEach-Object { Write-Host ('  backstop: stopped pid ' + \$_.ProcessId); Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }
" 2>/dev/null || true
taskkill //F //IM risk_engine.exe >/dev/null 2>&1 && echo "  backstop: stopped risk_engine.exe" || true

echo "stopping Docker infrastructure..."
docker compose stop

echo "done."
