from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BuyerAgent(Base):
    """A registered third-party buyer agent identity. api_key_hash is a
    SHA-256 digest — the plaintext key is shown exactly once, at
    registration, and never stored or logged anywhere.
    """

    __tablename__ = "buyer_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    buyer_agent_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    api_key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    # paise, per order; null = no ceiling. Not settable via /register — a
    # buyer can't declare its own limit — and not currently enforced by
    # any endpoint. Reserved for a future phase.
    spending_ceiling: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
