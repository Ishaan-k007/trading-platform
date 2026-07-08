import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app



from kafka import KafkaConsumer
import json,time,os
from config import Config
from enums import OrderStatus
from models import user, account, order, position, ledger_entry, market_price, risk_check
from extensions import db, jwt

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "order-fills")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "order-fill-consumer-group")


    
def process_fill(fill_data):
    fill_price = fill_data.get("fill_price")
    quantity = fill_data.get("quantity")
    new_cash = fill_data.get("new_cash")
    new_quantity = fill_data.get("new_quantity")
    new_avg_price = fill_data.get("new_avg_price")
    user_id = fill_data.get("user_id")
    symbol = fill_data.get("symbol")
    order_id = fill_data.get("order_id")
    side = fill_data.get("side")
    order_type = fill_data.get("order_type")
    
    new_order = order.Order(
        id=order_id,
        user_id=user_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        filled_price=fill_price,
        status=OrderStatus.FILLED,
        order_type=order_type,
        limit_price=None
    )
    db.session.add(new_order)
    acc = account.Account.query.filter_by(user_id=user_id).first()
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
    db.session.commit()
    
def main():
    app = create_app()
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_GROUP_ID,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True
    )
    with app.app_context():
        for message in consumer:
            process_fill(message.value)

if __name__ == "__main__": main()