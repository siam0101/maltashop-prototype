import json
import os
import threading
import time

import pika
from sqlalchemy.exc import IntegrityError

from app.db import Notification, ProcessedEvent, SessionLocal
from app.logging_config import correlation_id_var, get_logger

logger = get_logger()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://maltashop:maltashop@localhost:5672/")
EXCHANGE = "maltashop.events"
DLX = "maltashop.dlx"
QUEUE = "notification.order-placed"
DLQ = "notification.order-placed.dlq"
ROUTING_KEY = "order.placed"

consumer_state = {"connected": False}


def handle_order_placed(event: dict) -> None:
    event_id = event["event_id"]
    data = event["data"]

    with SessionLocal() as session:
        if session.get(ProcessedEvent, event_id):
            logger.info(
                "Duplicate event ignored",
                extra={"fields": {"event_id": event_id, "order_id": data["order_id"]}},
            )
            return

        session.add(
            Notification(
                order_id=data["order_id"],
                customer_id=data["customer_id"],
                channel="email",
                message=f"Thanks for your order {data['order_id']}. Total: EUR {data['total_amount']:.2f}",
                correlation_id=correlation_id_var.get(),
            )
        )
        session.add(ProcessedEvent(event_id=event_id))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            logger.info(
                "Duplicate event ignored",
                extra={"fields": {"event_id": event_id, "order_id": data["order_id"]}},
            )
            return

    logger.info(
        "Notification recorded",
        extra={"fields": {"event_id": event_id, "order_id": data["order_id"], "channel": "email"}},
    )


def on_message(channel, method, properties, body) -> None:
    token = None
    try:
        event = json.loads(body)
        correlation_id = properties.correlation_id or event.get("correlation_id") or "-"
        token = correlation_id_var.set(correlation_id)
        logger.info(
            "Event received",
            extra={"fields": {"event_type": event.get("event_type"), "event_id": event.get("event_id")}},
        )
        handle_order_placed(event)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception("Failed to process event, sending to dead-letter queue")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    finally:
        if token is not None:
            correlation_id_var.reset(token)


def run_consumer(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel = connection.channel()
            channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            channel.exchange_declare(exchange=DLX, exchange_type="fanout", durable=True)
            channel.queue_declare(queue=DLQ, durable=True)
            channel.queue_bind(queue=DLQ, exchange=DLX)
            channel.queue_declare(
                queue=QUEUE,
                durable=True,
                arguments={"x-dead-letter-exchange": DLX},
            )
            channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=ROUTING_KEY)
            channel.basic_qos(prefetch_count=10)
            channel.basic_consume(queue=QUEUE, on_message_callback=on_message)

            consumer_state["connected"] = True
            logger.info(
                "Listening for events",
                extra={"fields": {"queue": QUEUE, "routing_key": ROUTING_KEY}},
            )

            while not stop_event.is_set():
                connection.process_data_events(time_limit=1)
            connection.close()
        except Exception:
            consumer_state["connected"] = False
            logger.exception("RabbitMQ connection lost, retrying in 5 seconds")
            time.sleep(5)
    consumer_state["connected"] = False


def start_consumer() -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_consumer,
        args=(stop_event,),
        daemon=True,
        name="order-placed-consumer",
    )
    thread.start()
    return thread, stop_event