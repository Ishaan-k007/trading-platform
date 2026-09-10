#!/usr/bin/env bash
#
# Build the C++ risk engine into risk_engine_cpp/build/risk_engine.exe.
#
# Run from an MSYS2 UCRT64 shell — the engine links against the UCRT64
# gRPC / Protobuf / libpq packages (see README "Prerequisites"). CMake
# regenerates the C++ protobuf stubs from trading.proto as part of the build.
#
#   bash scripts/build_engine.sh
#
set -euo pipefail

cd "$(dirname "$0")/../risk_engine_cpp"

for tool in cmake ninja protoc; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "'$tool' not found. From an MSYS2 UCRT64 shell, run:" >&2
    echo "  pacman -S mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja \\" >&2
    echo "            mingw-w64-ucrt-x86_64-grpc mingw-w64-ucrt-x86_64-protobuf \\" >&2
    echo "            mingw-w64-ucrt-x86_64-postgresql" >&2
    exit 1
  }
done

cmake -S . -B build -G Ninja
ninja -C build

echo "Built: risk_engine_cpp/build/risk_engine.exe"
