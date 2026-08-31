from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Approval(Base):
    """A full record of every /evaluate call — both approved and rejected —
    kept independently of the backend's audit log. approval_token is only
    ever populated on approval, is unique, and is consumed (used=True) the
    first time it's verified so it cannot be replayed.
    """

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Who this approval was actually granted to, if the caller identified
    # itself — NULL for human negotiation sessions (no buyer identity
    # exists there). When set, /verify requires it to match on redemption
    # (see Phase 8's red-team report: cross-buyer token theft was possible
    # before this field existed, since nothing else here is buyer-scoped).
    requester_id: Mapped[str | None] = mapped_column(String, nullable=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cart_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)  # "approved" | "rejected"
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    final_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # paise, only set when approved
    approval_token: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True, index=True)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
