import json
import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_orders.db"

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import Base, engine

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "order_placed.json").read_text()
)

ORDER = {"customer_id": "cust-1", "product_id": "prod-1", "quantity": 2, "unit_price": 10.50}


@pytest.fixture
def published(monkeypatch):
    events = []

    def fake_publish(event_type, routing_key, data):
        events.append({"event_type": event_type, "routing_key": routing_key, "data": data})
        return "test-event-id"

    monkeypatch.setattr(main, "publish_event", fake_publish)
    return events


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_new_order_is_pending_with_correct_total(client, published):
    response = client.post("/orders", json=ORDER, headers={"Idempotency-Key": "k1"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["total_amount"] == 21.0


def test_same_idempotency_key_returns_same_order(client, published):
    first = client.post("/orders", json=ORDER, headers={"Idempotency-Key": "k2"})
    second = client.post("/orders", json=ORDER, headers={"Idempotency-Key": "k2"})
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["order_id"] == second.json()["order_id"]
    assert len(published) == 1


def test_invalid_quantity_is_rejected(client, published):
    response = client.post("/orders", json={**ORDER, "quantity": 0})
    assert response.status_code == 422
    assert published == []


def test_correlation_id_is_passed_through(client, published):
    response = client.post("/orders", json=ORDER, headers={"X-Correlation-ID": "abc-123"})
    assert response.headers["X-Correlation-ID"] == "abc-123"
    assert response.json()["correlation_id"] == "abc-123"


def test_order_placed_event_matches_contract(client, published):
    client.post("/orders", json=ORDER, headers={"Idempotency-Key": "k3"})
    event = published[0]
    assert event["event_type"] == CONTRACT["event_type"]
    assert event["routing_key"] == CONTRACT["routing_key"]
    for field, type_name in CONTRACT["data_fields"].items():
        assert field in event["data"]
        assert type(event["data"][field]).__name__ == type_name