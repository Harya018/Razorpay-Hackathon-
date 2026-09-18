from datetime import datetime, timezone

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CustomerProfile(Base):
    """The only user-editable profile data this backend stores — keyed by
    the verified Supabase `sub`, never by anything the client claims.
    Name/email/avatar/provider live in the Supabase token itself and are
    read from there; this table only holds what the token can't carry:
    a display name override and the contact/shipping details an order
    needs. Merchants may read a customer's row only through the
    admin-gated order-detail route, and only for orders they actually
    hold.
    """

    __tablename__ = "customer_profiles"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    pincode: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
