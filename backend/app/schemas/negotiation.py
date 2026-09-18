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
    order_id: Optional[int] = None


class NegotiationSessionStatus(BaseModel):
    session_id: str
    exists: bool  # False = this process has no checkpoint for this session_id at all (never existed here, or a restart since)
    expired: bool  # True = tracked by this process but past SESSION_MAX_AGE_SECONDS
    resumable: bool  # exists and not expired and the graph is actually paused (not already closed)
    created_at: Optional[float] = None  # unix seconds — None if this process never tracked this session's creation
    expires_at: Optional[float] = None
    session_max_age_seconds: int
