import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kafka import KafkaProducer
import json,time,os
import websocket
from decimal import Decimal
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_MARKET_TOPIC = os.getenv("KAFKA_MARKET_TOPIC", "market-ticks")

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
STREAMS = "/".join(f"{symbol.lower()}@trade" for symbol in SYMBOLS)
BINANCE_WS_URL = f"wss://stream.binance.com:9443/stream?streams={STREAMS}"

def handle_tick(producer, raw_message):
    
    """Parse a raw Binance trade message and publish it to Kafka.

    Binance sends combined-stream frames as JSON strings with prices
    encoded as decimal strings (not floats), to avoid binary
    floating-point rounding on money values.

    Args:
        producer: KafkaProducer instance used to publish the parsed tick.
        raw_message: Raw JSON string received from the Binance WebSocket,
            shaped like {"stream": "...", "data": {"s": ..., "p": ..., "T": ...}}.

    Malformed frames are logged and skipped rather than raised, so a single
    bad message doesn't kill the feed connection.
    """

    try:
        msg = json.loads(raw_message)
        data = msg["data"]
        symbol = data["s"]
        price = Decimal(data["p"])
        trade_time = data["T"]

        payload = {
            "symbol": symbol,
            "price": str(price),
            "trade_time": trade_time,
        }
        producer.send(KAFKA_MARKET_TOPIC, value=payload)

    except (json.JSONDecodeError, KeyError) as e:
        print(f"Skipping malformed tick: {e}")
    
    
def on_message(ws, message):
    handle_tick(ws.producer, message)

def on_error(ws, error):
    print(f"WebSocket error: {error}")
def on_close(ws, close_status_code, close_msg):
    print(f"WebSocket closed: {close_status_code} - {close_msg}")
def on_open(ws):
    print("WebSocket connection opened.")

def main():
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    while True:
        ws_app = websocket.WebSocketApp(
            BINANCE_WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws_app.producer = producer  # lets on_message reach it via ws.producer

        ws_app.run_forever()

        print("Disconnected, reconnecting in 5s...")
        time.sleep(5)

if __name__ == "__main__":
    main()
        