from pydantic import BaseModel, Field


class OrderCreateRequest(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class OrderCreateResponse(BaseModel):
    razorpay_order_id: str
    amount: int
    key_id: str
