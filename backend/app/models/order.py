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
    buyer_agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Signed-in customer who placed the order — the verified Supabase `sub`
    # claim, taken from the bearer token at /order/create, NEVER from the
    # request body. NULL for un-authenticated (guest) checkouts and for
    # agent-channel orders (which are identified by buyer_agent_id instead).
    # GET /orders filters on this, so a customer only ever sees their own.
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    user_email: Mapped[str | None] = mapped_column(String, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Catalog unit price at the moment the order was created — a snapshot,
    # so an invoice stays correct even if the merchant later edits the
    # product's price. amount (above) is what was actually charged.
    unit_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # policy-gate's own Approval.id for the redeemed token, if a discount
    # was applied — a safe cross-service reference (NOT the token itself).
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # The platform's own post-payment lifecycle (placed -> processing ->
    # shipped -> out_for_delivery -> delivered), set by the merchant. This
    # is NOT an external courier integration — none exists — just a
    # persisted, timestamped status the merchant advances by hand. NULL
    # until the order is paid.
    fulfillment_status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
