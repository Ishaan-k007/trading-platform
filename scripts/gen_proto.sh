#!/usr/bin/env bash
#
# Regenerate the Python gRPC stubs (services/trading_pb2.py,
# services/trading_pb2_grpc.py) from risk_engine_cpp/proto/trading.proto.
#
# The C++ stubs are regenerated automatically by CMake on every build; only
# the Python side needs this script. Run it whenever you edit trading.proto,
# then commit the regenerated files.
#
#   bash scripts/gen_proto.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# grpc_tools ships in the project venv (grpcio-tools is a main dependency).
# Prefer `poetry run`; fall back to the venv's python directly since Poetry
# often isn't on PATH inside the MSYS2 shell.
run_py() {
  if command -v poetry >/dev/null 2>&1; then
    poetry run python "$@"
    return
  fi
  local base m
  for base in "${LOCALAPPDATA:-}" "$HOME/AppData/Local"; do
    [[ -n "$base" ]] || continue
    base="$(cygpath -u "$base" 2>/dev/null || echo "$base")"
    m="$(ls -d "$base"/pypoetry/Cache/virtualenvs/trading-platform-* 2>/dev/null | head -1 || true)"
    if [[ -n "$m" && -x "$m/Scripts/python.exe" ]]; then "$m/Scripts/python.exe" "$@"; return; fi
    if [[ -n "$m" && -x "$m/bin/python" ]]; then "$m/bin/python" "$@"; return; fi
  done
  echo "Could not find the project virtualenv. Run 'poetry install' first." >&2
  exit 1
}

run_py -m grpc_tools.protoc \
  -I risk_engine_cpp/proto \
  --python_out=services \
  --grpc_python_out=services \
  risk_engine_cpp/proto/trading.proto

echo "Regenerated services/trading_pb2.py and services/trading_pb2_grpc.py"
