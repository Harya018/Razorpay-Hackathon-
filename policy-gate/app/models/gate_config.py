from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GateConfig(Base):
    """Singleton row (id always 1) holding the merchant's adjustable,
    not-per-product policy gate settings — the default discount cap and
    the max negotiation attempts. Seeded once at startup from
    app/rules/merchant_rules.py's hardcoded DEFAULT_RULE/MAX_ATTEMPTS
    (see seed_defaults_if_empty below); this table is the live source of
    truth after that, editable via PUT /rules/default. evaluate.py's
    actual decision logic is UNCHANGED by this — it still only ever
    compares against a max_discount_pct/max_attempts number, exactly as
    before; this only makes those numbers admin-editable instead of
    hardcoded.
    """

    __tablename__ = "gate_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    default_max_discount_pct: Mapped[float] = mapped_column(Float, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class ProductRuleOverride(Base):
    """Per-product override of GateConfig.default_max_discount_pct — one
    row per SKU that has its own discount cap and/or an absolute floor
    price, admin-editable via PUT/DELETE /rules/product/{product_id}. The
    absence of a row for a product_id means "use the default rule," never
    "no limit" — evaluate.py/merchant_rules.py always resolve to some
    concrete floor, there is no unbounded-discount code path.
    """

    __tablename__ = "product_rule_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    max_discount_pct: Mapped[float] = mapped_column(Float, nullable=False)
    floor_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # paise, per unit
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
