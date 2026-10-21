from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import select

from app.consumer import consumer_state, start_consumer
from app.db import Notification, SessionLocal, init_db
from app.logging_config import get_logger

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    thread, stop_event = start_consumer()
    logger.info("Notification service started")
    yield
    stop_event.set()
    thread.join(timeout=5)
    logger.info("Notification service stopped")


app = FastAPI(title="MaltaShop Notification Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "notification-service"}


@app.get("/ready")
def ready(response: Response):
    if not consumer_state["connected"]:
        response.status_code = 503
        return {"status": "not ready", "broker": "disconnected"}
    return {"status": "ready", "broker": "connected"}


@app.get("/notifications")
def list_notifications(order_id: str | None = None):
    with SessionLocal() as session:
        query = select(Notification).order_by(Notification.created_at.desc())
        if order_id:
            query = query.where(Notification.order_id == order_id)
        rows = session.scalars(query.limit(50)).all()
        return [
            {
                "id": n.id,
                "order_id": n.order_id,
                "customer_id": n.customer_id,
                "channel": n.channel,
                "message": n.message,
                "correlation_id": n.correlation_id,
                "created_at": n.created_at,
            }
            for n in rows
        ]