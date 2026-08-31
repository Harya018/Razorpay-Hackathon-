from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class NegotiateStartRequest(BaseModel):
    product_id: int
    cart_quantity: int = 1


class ProposedOfferSchema(BaseModel):
    type: Literal["discount", "bundle", "none"]
    value: Optional[int] = None
    reasoning: str


class NegotiateStartResponse(BaseModel):
    session_id: str
    message: str
    proposed_offer: Optional[ProposedOfferSchema] = None
    offer_status: Literal["none", "proposed", "accepted", "rejected", "countered"]
    turn_count: int


class NegotiateMessageRequest(BaseModel):
    session_id: str
    user_message: str


class NegotiateMessageResponse(BaseModel):
    session_id: str
    message: str
    proposed_offer: Optional[ProposedOfferSchema] = None
    offer_status: Literal["none", "proposed", "accepted", "rejected", "countered"]
    turn_count: int
    closed: bool
    handoff: bool
    checkout_amount: Optional[int] = None
    approval_token: Optional[str] = None


class AuditLogEntry(BaseModel):
    id: int
    event_type: str
    payload: dict
    created_at: datetime
