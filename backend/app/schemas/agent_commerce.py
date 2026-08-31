"""Pydantic models for /agent/v1/*. Field names, types, and nullability
here must match docs/agent-commerce-interface.md byte-for-byte — that
document IS the contract, this is just its enforcement in code.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: int  # paise
    currency: Literal["INR"] = "INR"
    stock: int
    negotiable: bool = True
    # Honesty-boundary marker (docs/x402-conformance-diff.md), carried
    # directly in the API response an agent sees FIRST — before it ever
    # reaches a payment endpoint — not just buried in payment-flow
    # objects or docs. Every item in this catalog settles via Razorpay
    # fiat rails, never on-chain; this field states that plainly at the
    # point an agent decides whether to transact at all.
    settlement_type: Literal["fiat"] = "fiat"


class RegisterRequest(BaseModel):
    buyer_agent_id: str
    display_name: Optional[str] = None


class RegisterResponse(BaseModel):
    buyer_agent_id: str
    api_key: str
    created_at: datetime


class ProposedTerms(BaseModel):
    type: Literal["discount", "bundle"]
    value: int = Field(gt=0)  # paise, final total price for the cart


class NegotiateRequest(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    buyer_agent_id: str
    proposed_terms: ProposedTerms
    # Phase 11 — optional free-text message from the buyer agent, e.g.
    # "Hi, I'm interested in the Wireless Headphones. My budget is
    # ₹2000." Used ONLY to make the seller's reply message read like an
    # actual conversation (product name, price, negotiate-or-not framing)
    # — never fed into the deterministic gate decision, which still only
    # ever looks at proposed_terms.type/value. Omit it and this endpoint
    # behaves exactly as it always has.
    message: Optional[str] = None


class FinalTerms(BaseModel):
    type: Literal["discount", "bundle"]
    value: int


class NegotiateResponse(BaseModel):
    approved: bool
    approval_token: Optional[str] = None
    final_terms: Optional[FinalTerms] = None
    reason: Optional[str] = None
    max_allowed: Optional[int] = None
    # Phase 11 — a natural-language reply mentioning the product and
    # price, generated AFTER the deterministic approved/reason/max_allowed
    # decision above (never influences it). Best-effort: if the LLM call
    # fails, this is null and every other field is unaffected.
    message: Optional[str] = None


class PurchaseRequest(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    buyer_agent_id: str
    approval_token: Optional[str] = None


class PurchaseTermsResponse(BaseModel):
    amount: int
    currency: Literal["INR"] = "INR"
    accepted_payment_methods: list[str] = ["razorpay_order"]
    payment_endpoint: str = "/agent/v1/pay"
    terms_reference: str


class PayRequest(BaseModel):
    terms_reference: str
    approval_token: Optional[str] = None
    buyer_agent_id: str


class PayResponse(BaseModel):
    order_id: int
    razorpay_order_id: str
    status: str
    amount: int


class OrderStatusResponse(BaseModel):
    order_id: int
    status: str
    amount: int
    razorpay_order_id: str
