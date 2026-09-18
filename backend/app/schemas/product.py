from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewSchema(BaseModel):
    author: str
    rating: float
    text: str


class ProductCreate(BaseModel):
    name: str
    price: int = Field(gt=0, description="Price in paise, integer only")
    stock: int = Field(ge=0)
    description: str | None = None
    # Phase 9 storefront fields — all optional so Phase 1's admin
    # POST /product flow (name/price/stock/description only) still works
    # unchanged; a product created without these just won't show a full
    # storefront detail page until an admin fills them in.
    category: str | None = None
    detail_description: str | None = None
    image_urls: list[str] | None = None
    rating: float | None = None
    review_count: int | None = None
    negotiable: bool = True
    reviews: list[ReviewSchema] | None = None


class ProductUpdate(BaseModel):
    """PATCH body — every field optional; only what's sent is changed.
    Price/stock keep the same integer-paise / non-negative rules as create.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: int | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    description: str | None = None
    category: str | None = None
    detail_description: str | None = None
    negotiable: bool | None = None
    is_active: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: int
    stock: int
    description: str | None
    created_at: datetime
    category: str | None = None
    detail_description: str | None = None
    image_urls: list[str] | None = None
    rating: float | None = None
    review_count: int | None = None
    negotiable: bool = True
    reviews: list[ReviewSchema] | None = None
    is_active: bool = True
    updated_at: datetime | None = None
