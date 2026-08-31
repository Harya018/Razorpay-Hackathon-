from typing import Literal, Optional, TypedDict


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class ProposedOffer(TypedDict):
    type: Literal["discount", "bundle", "none"]
    value: Optional[int]  # paise — for "discount", the final total price for the cart
    reasoning: str


class NegotiationState(TypedDict):
    session_id: str
    product_id: int
    cart_quantity: int
    original_price: int  # paise, per unit — locked in at negotiation start
    hesitation_signal: str
    conversation_history: list[Message]
    proposed_offer: Optional[ProposedOffer]
    offer_status: Literal["none", "proposed", "accepted", "rejected", "countered"]
    turn_count: int
    # Set by propose_offer only when the policy gate approves the current
    # proposed_offer; consumed by /order/create via the gate's /verify.
    # Never trust this for anything other than "hand it back to the gate."
    approval_token: Optional[str]
