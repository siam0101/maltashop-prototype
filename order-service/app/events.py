import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import pika

from app.logging_config import correlation_id_var, get_logger

logger = get_logger()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://maltashop:maltashop@localhost:5672/")
EXCHANGE = "maltashop.events"


def publish_event(event_type: str, routing_key: str, data: dict) -> str:
    event_id = str(uuid4())
    correlation_id = correlation_id_var.get()
    body = {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "data": data,
    }

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(body, default=str),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
                message_id=event_id,
                correlation_id=correlation_id,
                type=event_type,
            ),
        )
    finally:
        connection.close()

    logger.info(
        "Event published",
        extra={"fields": {"event_type": event_type, "event_id": event_id, "routing_key": routing_key}},
    )
    return event_id