import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app



from kafka import KafkaConsumer
import json,time,os,traceback
from sqlalchemy.exc import IntegrityError
from config import Config
from core.money import to_decimal
from enums import OrderStatus
from models import user, account, order, position, ledger_entry, market_price, risk_check
from extensions import db, jwt

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "order-fills")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "order-fill-consumer-group")

# Reconnect backoff, doubling from the first to the second on repeated failure.
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 30
# How long a connection must survive before it counts as healthy enough to
# reset the backoff.
HEALTHY_SECONDS = 60


    
def process_fill(fill_data):
    # The engine works in doubles and the WAL carries them as JSON numbers.
    # This is the boundary where they become exact decimals at the platform's
    # fixed scale - see core/money.py for the rounding policy.
    fill_price = to_decimal(fill_data.get("fill_price"))
    quantity = to_decimal(fill_data.get("quantity"))
    new_cash = to_decimal(fill_data.get("new_cash"))
    new_quantity = to_decimal(fill_data.get("new_quantity"))
    new_avg_price = to_decimal(fill_data.get("new_avg_price"))
    user_id = fill_data.get("user_id")
    symbol = fill_data.get("symbol")
    order_id = fill_data.get("order_id")
    side = fill_data.get("side")
    order_type = fill_data.get("order_type")
    client_order_id = fill_data.get("client_order_id")
    event_id = fill_data.get("event_id")
    account_sequence = fill_data.get("account_sequence")


    # Idempotency: wal_producer.py saves its file cursor only *after* a
    # successful Kafka send, so a crash in between replays the last line on
    # restart. If this fill is already in the DB, skip it rather than crash on
    # the duplicate primary key (which would wedge every later fill behind it).
    if db.session.get(order.Order, order_id) is not None:
        print(f"[fill_consumer] order {order_id} already applied, skipping")
        return
    if client_order_id and order.Order.query.filter_by(
            idempotency_key=client_order_id).first() is not None:
        print(f"[fill_consumer] client_order_id {client_order_id} already applied, skipping")
        return


    acc = account.Account.query.filter_by(user_id=user_id).first()
    if acc is None:
        print(f"[fill_consumer] no account for user {user_id}, skipping order {order_id}")
        return

    new_order = order.Order(
        id=order_id,
        user_id=user_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        filled_price=fill_price,
        status=OrderStatus.FILLED,
        order_type=order_type,
        limit_price=None,
        idempotency_key=client_order_id,

    )
    db.session.add(new_order)
    acc.cash_balance = new_cash
    pos = position.Position.query.filter_by(user_id=user_id, symbol=symbol).first()
    if pos:
        pos.quantity = new_quantity
        pos.average_price = new_avg_price
    else:
        db.session.add(position.Position(
            user_id=user_id, symbol=symbol,
            quantity=new_quantity, average_price=new_avg_price
        ))
    try:
        db.session.commit()
    except IntegrityError:
        # Lost the race to another delivery of the same fill — the other one
        # won, this one is a no-op.
        db.session.rollback()
        print(f"[fill_consumer] order {order_id} already applied (raced), skipping")
    
def build_consumer():
    return KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_GROUP_ID,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True
    )


def main():
    """Consume fills forever, surviving broker problems.

    This process used to be a single `for message in consumer:` loop. Any
    exception killed it, and because the rest of the stack carries on happily -
    the engine keeps filling orders, wal_producer keeps publishing, the
    dashboard keeps drawing its charts from the CSV logs - a dead consumer is
    close to invisible. The only symptom is that PostgreSQL quietly stops
    changing while every screen still looks healthy.

    That is exactly what happened: kafka-python raised
    `ValueError: Invalid file descriptor: -1` from its selector during consumer
    group coordination, after a broker connection closed underneath it, and the
    process exited. Fills accumulated in Kafka for as long as nobody noticed.

    Reconnecting is safe because process_fill() is idempotent: it skips a fill
    whose order id or client_order_id is already applied, and the unique
    constraint on orders.idempotency_key catches anything past those checks. So
    re-reading uncommitted offsets after a crash costs nothing.
    """
    app = create_app()
    backoff = INITIAL_BACKOFF_SECONDS

    with app.app_context():
        while True:
            consumer = None
            connected_at = None
            try:
                consumer = build_consumer()
                connected_at = time.monotonic()
                print(f"[fill_consumer] listening on {KAFKA_TOPIC} "
                      f"at {KAFKA_BOOTSTRAP_SERVERS} (group {KAFKA_GROUP_ID})")

                for message in consumer:
                    try:
                        process_fill(message.value)
                    except Exception:
                        # One unapplyable message must not wedge every fill
                        # behind it. Roll back so the session is usable for the
                        # next one, and log loudly rather than failing silently.
                        db.session.rollback()
                        print(f"[fill_consumer] failed to apply {message.value!r}")
                        traceback.print_exc()

            except KeyboardInterrupt:
                print("[fill_consumer] stopping")
                return

            except Exception as error:
                # Reset the backoff only if the connection had been healthy for
                # a while. Without that, a consumer that connects and dies
                # immediately would retry in a tight loop forever.
                if connected_at and time.monotonic() - connected_at > HEALTHY_SECONDS:
                    backoff = INITIAL_BACKOFF_SECONDS

                print(f"[fill_consumer] consumer failed "
                      f"({type(error).__name__}: {error}); "
                      f"reconnecting in {backoff}s")
                traceback.print_exc()
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

            finally:
                if consumer is not None:
                    try:
                        consumer.close()
                    except Exception:
                        pass    # already broken; nothing useful to do


if __name__ == "__main__": main()