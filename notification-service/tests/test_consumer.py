import json
import os
from pathlib import Path

os.environ["NOTIFICATION_DB_PATH"] = "./test_notifications.db"

from sqlalchemy import select

from app.consumer import handle_order_placed
from app.db import Base, Notification, ProcessedEvent, SessionLocal, engine

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "order_placed.json").read_text()
)


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_contract_example_has_every_field_the_consumer_needs():
    event = CONTRACT["example"]
    for field in CONTRACT["envelope_fields"]:
        assert field in event
    for field in CONTRACT["data_fields"]:
        assert field in event["data"]


def test_order_placed_event_creates_one_notification():
    handle_order_placed(CONTRACT["example"])
    with SessionLocal() as session:
        notifications = session.scalars(select(Notification)).all()
    assert len(notifications) == 1
    assert notifications[0].order_id == CONTRACT["example"]["data"]["order_id"]
    assert "99.98" in notifications[0].message


def test_duplicate_event_is_ignored():
    handle_order_placed(CONTRACT["example"])
    handle_order_placed(CONTRACT["example"])
    with SessionLocal() as session:
        notifications = session.scalars(select(Notification)).all()
        processed = session.scalars(select(ProcessedEvent)).all()
    assert len(notifications) == 1
    assert len(processed) == 1