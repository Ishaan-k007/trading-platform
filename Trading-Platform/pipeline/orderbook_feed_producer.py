import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, time, threading
import urllib.request
from datetime import datetime, timezone

import grpc
import websocket

from services import trading_pb2, trading_pb2_grpc

BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"
RISK_ENGINE_HOST = os.getenv("RISK_ENGINE_HOST", "localhost")
RISK_ENGINE_PORT = int(os.getenv("RISK_ENGINE_PORT", 50051))
SHARD_SIZE = int(os.getenv("ORDERBOOK_SHARD_SIZE", 100))


def discover_symbols():
    """Fetch every actively-trading USDT pair from Binance's exchangeInfo endpoint.

    Used instead of a hardcoded symbol list so the feed automatically covers
    Binance's current USDT universe rather than needing to be hand-maintained.

    Returns:
        Sorted list of symbol strings, e.g. ["AAVEUSDT", "BTCUSDT", ...].
    """
    with urllib.request.urlopen(BINANCE_EXCHANGE_INFO_URL, timeout=30) as response:
        payload = json.loads(response.read())

    return sorted(
        entry["symbol"]
        for entry in payload["symbols"]
        if entry["quoteAsset"] == "USDT" and entry["status"] == "TRADING"
    )


def shard_symbols(symbols, shard_size):
    """Split a symbol list into consecutive batches, one per WebSocket connection.

    Binance caps how many streams a single connection can carry, and spreading
    symbols across several connections also means one dropped connection only
    interrupts its own shard instead of the entire symbol universe.
    """
    return [symbols[i:i + shard_size] for i in range(0, len(symbols), shard_size)]


def build_stream_url(symbols):
    """Build a Binance combined-stream URL subscribing to partial depth for each symbol."""
    streams = "/".join(f"{symbol.lower()}@depth20@100ms" for symbol in symbols)
    return f"wss://stream.binance.com:9443/stream?streams={streams}"


def handle_depth_update(stub, raw_message):
    """Parse one Binance partial-depth snapshot and push it to the risk engine.

    Partial-depth payloads don't include the symbol inside `data` (unlike the
    diff-depth stream) - it has to be read off the `stream` field instead,
    e.g. "btcusdt@depth20@100ms" -> "BTCUSDT".

    Each message is a complete top-of-book snapshot, not an incremental update,
    so there's no local book state to merge here - the C++ OrderBook store on
    the receiving end just replaces whatever it was holding for this symbol.

    Malformed frames are logged and skipped rather than raised, so one bad
    message doesn't kill the shard's connection.
    """
    try:
        msg = json.loads(raw_message)
        symbol = msg["stream"].split("@")[0].upper()
        data = msg["data"]
        bids = [trading_pb2.PriceLevel(price=float(p), quantity=float(q)) for p, q in data["bids"]]
        asks = [trading_pb2.PriceLevel(price=float(p), quantity=float(q)) for p, q in data["asks"]]
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Skipping malformed depth update: {e}")
        return

    request = trading_pb2.OrderBookUpdateRequest(
        symbol=symbol,
        bids=bids,
        asks=asks,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        stub.UpdateOrderBook(request, timeout=2)
    except grpc.RpcError as e:
        print(f"Failed to push order book update for {symbol}: {e}")


def run_shard(shard_id, symbols, stub):
    """Run one Binance depth-stream connection for a batch of symbols, reconnecting on drop.

    Each shard is independent - a dropped connection only interrupts this
    shard's symbols, not the others. `stub` is shared across all shards;
    gRPC Python stubs are safe to call concurrently from multiple threads.
    """
    stream_url = build_stream_url(symbols)

    def on_message(ws, message):
        handle_depth_update(ws.stub, message)

    def on_error(ws, error):
        print(f"[shard {shard_id}] WebSocket error: {error}")

    def on_close(ws, close_status_code, close_msg):
        print(f"[shard {shard_id}] WebSocket closed: {close_status_code} - {close_msg}")

    def on_open(ws):
        print(f"[shard {shard_id}] Connected ({len(symbols)} symbols)")

    while True:
        ws_app = websocket.WebSocketApp(
            stream_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws_app.stub = stub  # lets on_message reach it via ws.stub

        ws_app.run_forever()

        print(f"[shard {shard_id}] Disconnected, reconnecting in 5s...")
        time.sleep(5)


def main():
    print("Discovering symbols from Binance...")
    symbols = discover_symbols()
    shards = shard_symbols(symbols, SHARD_SIZE)
    print(f"Found {len(symbols)} USDT symbols, split into {len(shards)} shard(s) of up to {SHARD_SIZE}")

    channel = grpc.insecure_channel(f"{RISK_ENGINE_HOST}:{RISK_ENGINE_PORT}")
    stub = trading_pb2_grpc.TradingServiceStub(channel)

    threads = [
        threading.Thread(target=run_shard, args=(shard_id, shard, stub), daemon=True)
        for shard_id, shard in enumerate(shards)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
