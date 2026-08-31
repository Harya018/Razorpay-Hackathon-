from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # paise, integer only
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Phase 9 storefront fields — all nullable/defaulted so the three
    # Phase 1-7 products (which predate this) keep working untouched
    # until the seed script backfills them. Static seed content only;
    # never LLM-generated at runtime (see seed_catalog.py).
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    detail_description: Mapped[str | None] = mapped_column(String, nullable=True)
    image_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list[str], placeholder/stock images only
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    negotiable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reviews: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list[{author, rating, text}], static seed data
