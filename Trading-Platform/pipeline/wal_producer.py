import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kafka import KafkaProducer
import json,time,os

WAL_PATH = os.getenv("WAL_PATH", "wal.log")
CURSOR_FILE = "wal.cursor"
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "order-fills")

def load_cursor():
    """Return the last saved byte offset into wal.log, or 0 if none exists."""
    if os.path.exists(CURSOR_FILE):
        with open(CURSOR_FILE) as f:
            return int(f.read().strip())
    return 0

def save_cursor(position):
    with open(CURSOR_FILE, "w") as f:
        f.write(str(position))
def main():
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8")
    )

    position = load_cursor()
    while True:
        if os.path.exists(WAL_PATH):
            with open(WAL_PATH, "r") as file:
                file.seek(position)
                while True:
                    line = file.readline()
                    if not line:
                        break
                    if line.strip():
                        data = json.loads(line)
                        producer.send(KAFKA_TOPIC, value=data)
                        producer.flush()
                        save_cursor(file.tell())
                        position = file.tell()
                        print(f"Sent to Kafka: {data}")
                        
            time.sleep(0.1)  # Sleep for a second before checking for new entries
                
        
        
        else:
            time.sleep(1)
            continue
    
if __name__ == "__main__":
    main()

