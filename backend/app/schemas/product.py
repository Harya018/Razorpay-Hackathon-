from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    name: str
    price: int = Field(gt=0, description="Price in paise, integer only")
    stock: int = Field(ge=0)
    description: str | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: int
    stock: int
    description: str | None
    created_at: datetime
