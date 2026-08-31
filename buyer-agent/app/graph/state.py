from typing import Literal, Optional, TypedDict

from app.client import CatalogItem, NegotiateResult, PayResult, PurchaseTerms


class BuyerState(TypedDict):
    goal: str
    # Test-harness knob only (see nodes.evaluate) — never something a real
    # integrator's client would expose; used to reliably exercise the
    # gate's rejection path in scenario 3 without depending on LLM mood.
    force_aggressive_negotiation: bool

    discovered_products: list[CatalogItem]

    match_found: bool
    chosen_product: Optional[CatalogItem]
    chosen_quantity: int

    should_negotiate: bool
    proposed_type: Optional[Literal["discount", "bundle"]]
    proposed_value: Optional[int]

    # Phase 10, Part C — an explicit budget the LLM extracted from the
    # shopper's own goal text (paise), e.g. "budget 2000 rupees" -> 200000.
    # None if the goal never stated one — in that case any gate-approved
    # price is treated as meeting target (nothing to compare against).
    target_budget: Optional[int]
    # 1-indexed; which rung of discount_ladder.py this negotiation is on.
    # 0 before any negotiate_round has run.
    negotiation_attempt: int
    negotiation_result: Optional[NegotiateResult]
    # Set after each negotiate_round call — drives the checkpoint routing.
    # "approved_but_below_target": gate approved a price, but it's still
    # above the shopper's stated budget — this is the NEW pause state this
    # phase adds (see graph/nodes.py's negotiate_round/
    # await_negotiate_checkpoint).
    offer_status: Optional[Literal["approved_meets_target", "approved_but_below_target", "rejected"]]

    # Human-facing text for whichever checkpoint is currently paused,
    # written by the node BEFORE the pause (interrupt() itself carries no
    # side effects on the replay path — see nodes.py's await_* functions).
    pending_message: str
    # Set by await_purchase_confirmation once the shopper has answered
    # the (separate, independent) pre-purchase confirmation checkpoint.
    purchase_decision: Optional[Literal["confirmed", "cancelled"]]

    purchase_terms: Optional[PurchaseTerms]
    pay_result: Optional[PayResult]

    outcome: str
