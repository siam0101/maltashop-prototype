from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import Order, SessionLocal, init_db
from app.logging_config import correlation_id_var, get_logger

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Order service started")
    yield


app = FastAPI(title="MaltaShop Order Service", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
    token = correlation_id_var.set(correlation_id)
    try:
        response = await call_next(request)
    finally:
        correlation_id_var.reset(token)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


class OrderCreate(BaseModel):
    customer_id: str = Field(..., examples=["cust-1001"])
    product_id: str = Field(..., examples=["prod-55"])
    quantity: int = Field(..., gt=0, examples=[2])
    unit_price: Decimal = Field(..., gt=0, examples=[49.99])


class OrderOut(BaseModel):
    order_id: str
    status: str
    customer_id: str
    product_id: str
    quantity: int
    total_amount: float
    correlation_id: str


def to_out(order: Order) -> OrderOut:
    return OrderOut(
        order_id=order.id,
        status=order.status,
        customer_id=order.customer_id,
        product_id=order.product_id,
        quantity=order.quantity,
        total_amount=float(order.total_amount),
        correlation_id=correlation_id_var.get(),
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "order-service"}


@app.post("/orders", response_model=OrderOut, status_code=201)
def place_order(
    payload: OrderCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = idempotency_key or str(uuid4())

    with SessionLocal() as session:
        existing = session.scalar(select(Order).where(Order.idempotency_key == key))
        if existing:
            logger.info(
                "Duplicate request, returning existing order",
                extra={"fields": {"order_id": existing.id, "idempotency_key": key}},
            )
            response.status_code = 200
            return to_out(existing)

        order = Order(
            idempotency_key=key,
            customer_id=payload.customer_id,
            product_id=payload.product_id,
            quantity=payload.quantity,
            total_amount=payload.unit_price * payload.quantity,
            status="PENDING",
        )
        session.add(order)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(Order).where(Order.idempotency_key == key))
            response.status_code = 200
            return to_out(existing)

    logger.info(
        "Order created",
        extra={"fields": {"order_id": order.id, "total_amount": float(order.total_amount)}},
    )
    return to_out(order)


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: str):
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return to_out(order)