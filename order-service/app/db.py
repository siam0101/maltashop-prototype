import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Integer, Numeric, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://order_user:order_pass@localhost:5432/orders",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass

class Order(Base):
    """An order. Only the Order service reads or writes this table (database per service)."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # The same key sent twice returns the same order instead of creating a duplicate.
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(50))
    product_id: Mapped[str] = mapped_column(String(50))
    quantity: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Starts as PENDING. In the full saga, Payment and Inventory events move it on.
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def init_db() -> None:
    """Create the orders table if it does not exist yet."""
    Base.metadata.create_all(engine)