import json
from typing import Literal, Optional

from langgraph.types import Command, interrupt
from pydantic import BaseModel

from app.client import client_from_settings
from app.graph import discount_ladder
from app.graph.state import BuyerState
from app.llm import call_structured


class EvaluateDecision(BaseModel):
    match_found: bool
    product_id: Optional[int] = None
    quantity: int = 1
    should_negotiate: bool = False
    proposed_type: Optional[Literal["discount", "bundle"]] = None
    proposed_value: Optional[int] = None
    # Phase 10, Part C — an explicit budget (paise) if the shopper's goal
    # states one (e.g. "under 2000 rupees", "budget is 2000"). None if no
    # number was stated — never guessed or inferred from the product price.
    target_budget: Optional[int] = None
    reasoning: str


def discover(state: BuyerState) -> dict:
    """Pure data fetch, no LLM call — mirrors the discipline of separating
    data-gathering from reasoning.
    """
    client = client_from_settings()
    products = client.get_catalog()
    return {"discovered_products": products}


def evaluate(state: BuyerState) -> Command[Literal["negotiate_round", "await_purchase_confirmation", "report"]]:
    products = state["discovered_products"]
    catalog_json = json.dumps(
        [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "currency": p.currency,
                "stock": p.stock,
                "negotiable": p.negotiable,
            }
            for p in products
        ],
        indent=2,
    )

    aggressive_note = ""
    if state.get("force_aggressive_negotiation"):
        aggressive_note = (
            "\n\nTEST MODE: if you decide the product is negotiable and worth "
            "negotiating, propose an aggressively low total price — at least 50% "
            "off list price. This is a deliberate test of how the merchant's "
            "policy gate handles an unreasonable ask, not normal behavior."
        )

    system = (
        "You are an autonomous shopping agent. Given a shopper's goal and a "
        "merchant's catalog, decide: (1) whether any product is a genuine match "
        "for the goal — do not force a match onto an unrelated product, (2) how "
        "many units to buy, (3) whether it's worth attempting to negotiate a "
        "better price, and (4) whether the shopper's goal states an explicit "
        "budget or price ceiling (e.g. 'under 2000 rupees', 'budget is 2000') — "
        "if so, extract it as target_budget in PAISE (rupees * 100); if no "
        "number is stated, leave target_budget null. Only propose negotiating "
        "if the chosen product has negotiable: true."
    )
    user = f"Shopper's goal: {state['goal']}\n\nCatalog:\n{catalog_json}{aggressive_note}"

    decision = call_structured(system, user, EvaluateDecision)

    if not decision.match_found or decision.product_id is None:
        return Command(
            update={
                "match_found": False,
                "outcome": (
                    f"No suitable product found for goal: '{state['goal']}'.\n"
                    f"Reasoning: {decision.reasoning}"
                ),
            },
            goto="report",
        )

    chosen = next((p for p in products if p.id == decision.product_id), None)
    if chosen is None:
        # The model named a product id that isn't actually in the catalog —
        # never trust that; treat it as no match rather than buy something
        # that doesn't exist.
        return Command(
            update={
                "match_found": False,
                "outcome": (
                    f"No suitable product found for goal: '{state['goal']}' "
                    "(model proposed a product id not present in the catalog)."
                ),
            },
            goto="report",
        )

    update = {
        "match_found": True,
        "chosen_product": chosen,
        "chosen_quantity": max(1, decision.quantity),
        "target_budget": decision.target_budget,
    }

    if decision.should_negotiate and chosen.negotiable and decision.proposed_type:
        update["should_negotiate"] = True
        update["proposed_type"] = decision.proposed_type
        update["proposed_value"] = decision.proposed_value
        if decision.proposed_type == "discount":
            # Ladder-driven from here — Part C's staged negotiation only
            # applies to straight discounts, same scope decision Part A
            # made on the seller side. Bundles keep the original
            # single-shot, LLM-proposed-value path (unaffected below).
            return Command(update=update, goto="negotiate_round")
        return Command(update=update, goto="_negotiate_bundle_once")

    update["should_negotiate"] = False
    total = chosen.price * update["chosen_quantity"]
    update["pending_message"] = (
        f"I found {chosen.name} at ₹{total / 100:.2f} — not negotiating on this one "
        f"({'not marked negotiable' if not chosen.negotiable else 'no negotiation attempted'}). "
        "Want me to go ahead and buy it, or cancel?"
    )
    return Command(update=update, goto="await_purchase_confirmation")


def _buyer_negotiation_message(
    product, quantity: int, proposed_value: int, target_budget: Optional[int]
) -> str:
    """Phase 11 — the buyer agent's own free-text chat opener, sent as
    NegotiateRequest.message so the seller agent's reply reads like an
    actual conversation. Purely presentational: the actual ask is still
    proposed_terms, built deterministically elsewhere, never parsed back
    out of this string by anyone.
    """
    budget_note = f" My budget is ₹{target_budget / 100:.2f}." if target_budget is not None else ""
    return (
        f"Hi, I'm interested in the {product.name} (x{quantity}).{budget_note} "
        f"I'd like to propose ₹{proposed_value / 100:.2f} total."
    )


def _seller_reply_suffix(result) -> str:
    """Appends the seller agent's own chat message (if it sent one) to a
    buyer-facing pending_message, so the human sees the actual AI-to-AI
    exchange rather than just this agent's own summary of it.
    """
    return f"\n\nSeller agent said: \"{result.message}\"" if getattr(result, "message", None) else ""


def _negotiate_bundle_once(state: BuyerState) -> Command[Literal["await_purchase_confirmation"]]:
    """The ORIGINAL Phase 4b single-shot negotiate path, unchanged, kept
    only for offer_type == 'bundle' — out of Part A/C's discount-ladder
    scope. Always lands on the (new, Phase 10) purchase-confirmation
    checkpoint afterward rather than buying immediately, same as every
    other path now.
    """
    client = client_from_settings()
    product = state["chosen_product"]
    quantity = state["chosen_quantity"]
    chat_message = _buyer_negotiation_message(product, quantity, state["proposed_value"], state.get("target_budget"))
    result = client.negotiate(
        product_id=product.id,
        quantity=quantity,
        proposed_type=state["proposed_type"],
        proposed_value=state["proposed_value"],
        message=chat_message,
    )
    if result.approved:
        price = (result.final_terms or {}).get("value")
        msg = f"The seller approved a bundle deal — ₹{(price or 0) / 100:.2f}. Buy at this price, or cancel?"
    else:
        full_price = product.price * quantity
        msg = (
            f"The seller declined the bundle proposal (reason: {result.reason}). "
            f"I can still buy at the listed price of ₹{full_price / 100:.2f}. Proceed, or cancel?"
        )
    msg += _seller_reply_suffix(result)
    return Command(update={"negotiation_result": result, "pending_message": msg}, goto="await_purchase_confirmation")


def negotiate_round(
    state: BuyerState,
) -> Command[Literal["await_negotiate_checkpoint", "await_purchase_confirmation"]]:
    """Runs ONE round of negotiation against the seller's stateless
    /agent/v1/negotiate — proposes the NEXT rung of this agent's own
    discount ladder (never an LLM-improvised number, mirroring Part A's
    principle on the buyer's side), then classifies the result against
    the shopper's stated budget to decide which checkpoint (if any) to
    pause at.
    """
    client = client_from_settings()
    product = state["chosen_product"]
    quantity = state["chosen_quantity"]
    attempt = state.get("negotiation_attempt", 0) + 1

    rung = discount_ladder.rung_for_attempt(attempt)
    proposed_value = discount_ladder.ladder_total_value(product.price, quantity, rung.discount_pct)
    target_budget = state.get("target_budget")

    chat_message = _buyer_negotiation_message(product, quantity, proposed_value, target_budget)
    result = client.negotiate(product.id, quantity, "discount", proposed_value, message=chat_message)
    final_value = (result.final_terms or {}).get("value") if result.approved else None

    if not result.approved:
        offer_status = "rejected"
    elif target_budget is None or (final_value is not None and final_value <= target_budget):
        offer_status = "approved_meets_target"
    else:
        offer_status = "approved_but_below_target"

    update = {
        "negotiation_result": result,
        "negotiation_attempt": attempt,
        "offer_status": offer_status,
    }

    full_price = product.price * quantity

    if offer_status == "approved_but_below_target" and not rung.is_final_rung:
        msg = (
            f"The seller's agent has come back with a {rung.discount_pct:g}% discount — "
            f"₹{final_value / 100:.2f} instead of ₹{full_price / 100:.2f}. That's still above "
            f"your budget of ₹{target_budget / 100:.2f}. Want me to keep negotiating, or should "
            "I go ahead and buy at this price?"
        )
        msg += _seller_reply_suffix(result)
        return Command(update={**update, "pending_message": msg}, goto="await_negotiate_checkpoint")

    if offer_status == "approved_but_below_target" and rung.is_final_rung:
        msg = (
            f"The seller says {rung.discount_pct:g}% is the best discount they can offer — "
            f"₹{final_value / 100:.2f}. That's still above your budget of ₹{target_budget / 100:.2f}. "
            "Do you want to buy at this price anyway, or cancel?"
        )
        msg += _seller_reply_suffix(result)
        return Command(update={**update, "pending_message": msg}, goto="await_purchase_confirmation")

    if offer_status == "approved_meets_target":
        budget_note = f" — within your ₹{target_budget / 100:.2f} budget" if target_budget is not None else ""
        msg = f"Good news — the seller approved a price of ₹{final_value / 100:.2f}{budget_note}. Buy at this price?"
        msg += _seller_reply_suffix(result)
        return Command(update={**update, "pending_message": msg}, goto="await_purchase_confirmation")

    # rejected
    msg = (
        f"The seller's agent declined to negotiate (reason: {result.reason}). "
        f"I can still buy at the listed price of ₹{full_price / 100:.2f}. Proceed, or cancel?"
    )
    msg += _seller_reply_suffix(result)
    return Command(update={**update, "pending_message": msg}, goto="await_purchase_confirmation")


def _classify_shopper_reply(reply: str) -> Literal["negotiate_more", "cancel", "confirm"]:
    """Deterministic keyword classification, not an LLM call — this is a
    controlled shopper-facing interface (two/three canonical choices are
    presented in the pending_message), so a small no-dependency parser is
    more predictable here than adding another model round-trip. Unknown
    replies default to "confirm" (proceed), never to silently cancelling
    or silently over-negotiating — the safer default when the intent is
    ambiguous is to do what was most recently, explicitly on offer.
    """
    lowered = reply.strip().lower()
    if any(kw in lowered for kw in ("negotiate", "keep going", "push", "try again", "more", "another")):
        return "negotiate_more"
    if any(kw in lowered for kw in ("cancel", "no thanks", "stop", "never mind", "nevermind", "don't", "not interested")):
        return "cancel"
    return "confirm"


def await_negotiate_checkpoint(
    state: BuyerState,
) -> Command[Literal["negotiate_round", "await_purchase_confirmation", "report"]]:
    """Phase 10, Part C's core checkpoint: the graph HALTS here whenever
    negotiate_round found an approved-but-below-target price with another
    ladder rung still available — it does NOT auto-continue negotiating
    on its own judgment. Only an explicit "negotiate more" reply from the
    person advances to the next rung; any other reply moves toward a
    purchase decision instead.
    """
    reply: str = interrupt({"awaiting": "negotiate_checkpoint", "message": state["pending_message"]})

    intent = _classify_shopper_reply(reply)
    if intent == "negotiate_more":
        return Command(goto="negotiate_round")
    if intent == "cancel":
        return Command(
            update={"purchase_decision": "cancelled", "outcome": "Shopper declined to continue negotiating."},
            goto="report",
        )
    # "confirm" here means "stop negotiating, proceed with the current
    # terms" — that still runs through the SEPARATE pre-purchase
    # confirmation checkpoint below, never skips it.
    result = state["negotiation_result"]
    product = state["chosen_product"]
    price = (result.final_terms or {}).get("value") if result and result.approved else product.price * state["chosen_quantity"]
    msg = f"Confirming purchase at ₹{price / 100:.2f}. Proceed?"
    return Command(update={"pending_message": msg}, goto="await_purchase_confirmation")


def await_purchase_confirmation(state: BuyerState) -> Command[Literal["purchase", "report"]]:
    """The pre-purchase confirmation checkpoint — independent of, and
    never skipped by, the mid-negotiation checkpoint above. Every path
    through this graph that could end in spending real money passes
    through here first.
    """
    reply: str = interrupt({"awaiting": "purchase_confirmation", "message": state["pending_message"]})

    intent = _classify_shopper_reply(reply)
    if intent == "cancel":
        return Command(
            update={"purchase_decision": "cancelled", "outcome": "Shopper declined to purchase."},
            goto="report",
        )
    return Command(update={"purchase_decision": "confirmed"}, goto="purchase")


def purchase(state: BuyerState) -> dict:
    """Always runs in the same graph invocation as negotiate (or is skipped
    straight to from evaluate for a non-negotiated buy) — never a separate
    process run reusing a token from an earlier invocation. This is how the
    documented token-freshness limitation is respected: by construction,
    not by an expiry mechanism the interface doesn't have.
    """
    client = client_from_settings()
    product = state["chosen_product"]
    quantity = state["chosen_quantity"]

    approval_token = None
    negotiation = state.get("negotiation_result")
    if negotiation and negotiation.approved:
        approval_token = negotiation.approval_token

    terms = client.purchase(product.id, quantity, approval_token)
    accepted = (terms.payment_required or {}).get("accepts", [None])[0]
    pay_result = client.pay(terms.terms_reference, approval_token, accepted=accepted)

    return {"purchase_terms": terms, "pay_result": pay_result}


def report(state: BuyerState) -> dict:
    if not state.get("match_found"):
        return {"outcome": state.get("outcome", "No suitable product found.")}

    if state.get("purchase_decision") == "cancelled":
        return {"outcome": state.get("outcome", "Shopper declined to purchase.")}

    product = state["chosen_product"]
    quantity = state["chosen_quantity"]
    negotiation = state.get("negotiation_result")
    pay_result = state.get("pay_result")

    lines = [
        f"Goal: {state['goal']}",
        f"Chosen product: {product.name} (id={product.id}) x{quantity}",
    ]

    if negotiation is None:
        lines.append("Negotiation: not attempted — bought at listed price.")
    elif negotiation.approved:
        lines.append(
            f"Negotiation: APPROVED — final_terms={negotiation.final_terms} "
            f"(attempt {state.get('negotiation_attempt')}, offer_status={state.get('offer_status')})"
        )
    else:
        lines.append(
            f"Negotiation: REJECTED — reason={negotiation.reason}, "
            f"max_allowed={negotiation.max_allowed}. Proceeded at listed price."
        )

    if pay_result:
        lines.append(
            f"Order created: order_id={pay_result.order_id}, "
            f"razorpay_order_id={pay_result.razorpay_order_id}, "
            f"status={pay_result.status}, "
            f"amount={pay_result.amount} paise (₹{pay_result.amount / 100:.2f})"
        )

    return {"outcome": "\n".join(lines)}
