from prometheus_client import Histogram

# Buckets in seconds, spanning the range we actually expect for this call
# (sub-millisecond in-memory work plus real gRPC/network round-trip).
EXECUTE_ORDER_LATENCY = Histogram(
    "execute_order_latency_seconds",
    "Round-trip latency of RiskEngineClient.execute_order (Flask -> C++ gRPC ExecuteOrder)",
    buckets=(
        100e-6, 200e-6, 300e-6, 500e-6,
        1e-3, 2e-3, 5e-3, 10e-3, 25e-3, 50e-3, 100e-3,
    ),
)

