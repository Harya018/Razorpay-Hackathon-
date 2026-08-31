from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    razorpay_order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise, integer only
    status: Mapped[str] = mapped_column(String, nullable=False, default="created")  # created | paid | failed
    # "human" (checkout page) | "agent" (POST /agent/v1/pay) — added Phase 6.
    # Existing rows default to "human" via the migration in database.py, since
    # every order created before Phase 4a's agent channel existed was human.
    channel: Mapped[str] = mapped_column(String, nullable=False, default="human")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
