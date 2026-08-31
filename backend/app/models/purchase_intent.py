from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PurchaseIntent(Base):
    """Created by POST /agent/v1/purchase (the 402 step), consumed exactly
    once by POST /agent/v1/pay. This is what terms_reference points to —
    it is NOT the payment authorization itself, just a record of "this
    buyer said they intend to buy this cart." approval_token here is
    whatever the buyer declared at /purchase time, kept for audit purposes
    only; the token that actually gets verified is the one supplied again
    to /pay (see gate_client.verify_token), not this stored copy.
    """

    __tablename__ = "purchase_intents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    terms_reference: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    buyer_agent_id: Mapped[str] = mapped_column(String, nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    declared_approval_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
