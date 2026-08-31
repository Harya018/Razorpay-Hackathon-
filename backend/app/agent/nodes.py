import json
import logging
import threading
import time
from typing import Literal, Optional, Type, TypeVar

import openai
from langgraph.types import Command, interrupt
from pydantic import BaseModel, ValidationError

from app import gate_client
from app.agent import discount_ladder, prompts
from app.agent.state import Message, NegotiationState, ProposedOffer
from app.audit import write_audit_log
from app.config import settings
from app.database import SessionLocal
from app.models.product import Product

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Safety bound on conversation length ONLY — this is NOT the policy gate.
# Phase 3's gate owns the real, enforced limit on what can be offered; this
# constant just stops the graph from looping forever during negotiation. It
# is a fixed constant in code, never adjustable by user input or the LLM.
MAX_OFFER_ATTEMPTS = 3

# (label, model, client) tuples, tried in order.
_providers: Optional[list[tuple[str, str, openai.OpenAI]]] = None

_T = TypeVar("_T", bound=BaseModel)

# Gemini's free tier caps at 15 requests/minute for gemini-3.1-flash-lite —
# far tighter than Groq's daily-token model. Hammering it above that rate
# just produces cascading 429s instead of usable fallback capacity, so
# every call actually routed to Gemini is paced to stay under that cap
# with a safety margin (15/min = 1 per 4s; we space at 4.5s).
GEMINI_MIN_INTERVAL_SECONDS = 4.5
_gemini_rate_lock = threading.Lock()
_last_gemini_call_at = 0.0


def _throttle_gemini() -> None:
    global _last_gemini_call_at
    with _gemini_rate_lock:
        now = time.monotonic()
        wait = GEMINI_MIN_INTERVAL_SECONDS - (now - _last_gemini_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_gemini_call_at = time.monotonic()


def _get_providers() -> list[tuple[str, str, openai.OpenAI]]:
    """Fallback chain, built lazily: primary Groq key, then a second Groq
    key if configured (same account/quota pool — only helps for non-quota
    errors), then Gemini via its OpenAI-compatible endpoint as a genuinely
    separate provider with its own quota. Each entry only exists if its
    key is actually configured.
    """
    global _providers
    if _providers is None:
        providers = [("groq-primary", settings.GROQ_MODEL, openai.OpenAI(api_key=settings.GROQ_API_KEY, base_url=GROQ_BASE_URL))]
        if settings.GROQ_API_KEY_2:
            providers.append(
                ("groq-fallback", settings.GROQ_MODEL, openai.OpenAI(api_key=settings.GROQ_API_KEY_2, base_url=GROQ_BASE_URL))
            )
        if settings.GEMINI_API_KEY:
            providers.append(
                ("gemini-fallback", settings.GEMINI_MODEL, openai.OpenAI(api_key=settings.GEMINI_API_KEY, base_url=GEMINI_BASE_URL))
            )
        _providers = providers
    return _providers


def _create_completion(messages: list[dict]) -> str:
    """Tries each configured provider in order, moving to the next on a
    rate-limit error OR on the provider being genuinely unreachable/down
    (connection error, timeout, 5xx) — Phase 18's demo-day resilience
    pass widened this from rate-limit-only after finding live that a
    plain Groq outage/timeout (not a 429) was NOT caught here at all and
    would crash the negotiation with an unhandled 500. A malformed
    response or an auth/config error (real bugs, not transient
    third-party flakiness) still surface immediately, not silently
    retried against a different provider.
    """
    providers = _get_providers()
    last_error: Optional[Exception] = None
    for i, (label, model, client) in enumerate(providers):
        if label == "gemini-fallback":
            _throttle_gemini()
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=1024,
                messages=messages,
                response_format={"type": "json_object"},
            )
            if i > 0:
                logger.warning("Earlier LLM provider(s) exhausted - served by fallback provider '%s' (%s)", label, model)
            return response.choices[0].message.content
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
            last_error = e
            logger.warning("Provider '%s' (%s) unavailable (%s), trying next if available: %s", label, model, type(e).__name__, e)
            continue
    assert last_error is not None  # unreachable with a non-empty providers list
    raise last_error


def _schema_instruction(schema: Type[BaseModel]) -> str:
    """Renders a flat Pydantic schema as a human/LLM-readable JSON shape
    description. Used with plain JSON-object mode rather than provider-strict
    schema mode, since strict json_schema mode on Groq is currently limited
    to a couple of specific models — this keeps the negotiation agent
    portable across whichever Groq (or other OpenAI-compatible) model is
    configured.
    """
    props = schema.model_json_schema().get("properties", {})
    lines = []
    for name, spec in props.items():
        if "enum" in spec:
            type_desc = " | ".join(f'"{v}"' for v in spec["enum"])
        elif "anyOf" in spec:
            type_desc = " | ".join(s.get("type", "null") for s in spec["anyOf"])
        else:
            type_desc = spec.get("type", "any")
        lines.append(f'  "{name}": {type_desc}')
    return "Respond with ONLY a single JSON object, no other text, matching exactly this shape:\n{\n" + ",\n".join(lines) + "\n}"


class StructuredOutputError(RuntimeError):
    """The LLM's structured output couldn't be parsed/validated even after
    one corrective retry. Empirically rare (0/24 in a manual reliability
    check across all three schemas), but Phase 3's gate will be parsing this
    exact kind of object to enforce limits, so a malformed-output failure
    needs to be a distinguishable, catchable error — not a raw
    JSONDecodeError/ValidationError bubbling up as an unhandled 500 — so a
    caller can choose to treat it as "no valid proposal was produced" rather
    than discover the shape of the failure live.
    """


def _call_structured(system: str, user: str, schema: Type[_T]) -> _T:
    full_user = f"{user}\n\n{_schema_instruction(schema)}"
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": full_user},
    ]

    last_error: Optional[Exception] = None
    for attempt in range(2):  # one retry on malformed/invalid structured output
        try:
            content = _create_completion(messages)
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
            # Every configured provider (Groq, Groq-2, Gemini) is
            # exhausted/unreachable — this is exactly the "Groq is down"
            # demo-day scenario, not a malformed-output bug. Wrapped as
            # StructuredOutputError so every existing call site's
            # `except StructuredOutputError` already handles it, same as
            # a parse failure — see nodes.py's DEMO_FALLBACK_MODE call
            # sites for how this degrades into a canned response instead
            # of aborting when that flag is on.
            raise StructuredOutputError(f"All configured LLM providers unavailable for {schema.__name__}: {e}") from e
        try:
            return schema.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            messages = messages + [
                {"role": "assistant", "content": content or ""},
                {
                    "role": "user",
                    "content": (
                        "That response could not be parsed as valid JSON matching "
                        f"the required shape (error: {e}). Respond again with ONLY "
                        "the corrected JSON object, nothing else."
                    ),
                },
            ]

    raise StructuredOutputError(
        f"Groq returned unparseable output for {schema.__name__} twice in a row: {last_error}"
    )


class DecideToOfferOutput(BaseModel):
    should_offer: bool
    offer_shape: Literal["discount", "bundle", "none"]
    reasoning: str


class ProposeOfferOutput(BaseModel):
    message: str
    offer_type: Literal["discount", "bundle", "none"]
    offer_value: Optional[int] = None
    offer_reasoning: str


class ProposeDiscountMessageOutput(BaseModel):
    """Phase 10: used ONLY for offer_shape == 'discount'. The percentage
    (and therefore offer_value) is decided deterministically by
    discount_ladder, not the LLM — this schema deliberately has no value
    field to choose; the LLM's only job is the natural-language framing.
    """

    message: str
    offer_reasoning: str


class HandleResponseOutput(BaseModel):
    intent: Literal["accept", "reject", "counter", "off_topic"]
    reply_message: str
    reasoning: str


class CustomerMindsetOutput(BaseModel):
    summary: str


class AgentNegotiationMessageOutput(BaseModel):
    """Phase 11 — used ONLY to frame /agent/v1/negotiate's reply as a
    natural chat message for the AI-to-AI negotiation flow. The LLM is
    given an already-final approved/reason/max_allowed decision and may
    only narrate it, never choose or alter a number itself.
    """

    message: str


def _cart_summary(state: NegotiationState, product: Product) -> str:
    total = state["original_price"] * state["cart_quantity"]
    return (
        f"Product: {product.name}\n"
        f"Quantity: {state['cart_quantity']}\n"
        f"Unit price: {state['original_price'] / 100:.2f} INR\n"
        f"Original total: {total / 100:.2f} INR\n"
        f"Stock available: {product.stock}"
    )


def _history_summary(history: list[Message]) -> str:
    if not history:
        return ""
    lines = []
    for msg in history:
        speaker = "Shopper" if msg["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {msg['content']}")
    return "\n".join(lines)


def _offer_summary(offer: Optional[ProposedOffer]) -> str:
    if not offer:
        return "(no offer currently on the table)"
    if offer["type"] == "none":
        return "(no discount offered — assistant explained nothing special was available)"
    value = offer.get("value")
    value_str = f"final total {value / 100:.2f} INR" if value is not None else "(no numeric value given)"
    return f"Offer type: {offer['type']}, {value_str}. Reasoning given to shopper: {offer['reasoning']}"


def assess_cart(state: NegotiationState) -> dict:
    db = SessionLocal()
    try:
        product = db.get(Product, state["product_id"])
        if product is None:
            raise ValueError(f"Product {state['product_id']} not found")

        write_audit_log(
            db,
            order_id=None,
            event_type="cart_assessed",
            payload={
                "session_id": state["session_id"],
                "product_id": product.id,
                "product_name": product.name,
                "quantity": state["cart_quantity"],
                "unit_price": product.price,
                "stock": product.stock,
            },
        )
        return {}
    finally:
        db.close()


def decide_to_offer(state: NegotiationState) -> Command[Literal["propose_offer", "close_negotiation"]]:
    db = SessionLocal()
    try:
        if state["turn_count"] >= MAX_OFFER_ATTEMPTS:
            write_audit_log(
                db,
                order_id=None,
                event_type="offer_decision",
                payload={
                    "session_id": state["session_id"],
                    "should_offer": False,
                    "offer_shape": "none",
                    "reasoning": "Conversation-length safety bound reached; no further offer attempts.",
                    "attempt_number": state["turn_count"] + 1,
                },
            )
            closing_note = (
                "I'm not able to offer anything further right now, but the last "
                "price I quoted is still available whenever you're ready."
            )
            history_with_note = state["conversation_history"] + [
                {"role": "assistant", "content": closing_note}
            ]
            return Command(update={"conversation_history": history_with_note}, goto="close_negotiation")

        product = db.get(Product, state["product_id"])
        cart_summary = _cart_summary(state, product)
        history_summary = _history_summary(state["conversation_history"])

        try:
            decision = _call_structured(
                system=prompts.decide_to_offer_system(),
                user=prompts.decide_to_offer_user(cart_summary, history_summary),
                schema=DecideToOfferOutput,
            )
        except StructuredOutputError as e:
            if not settings.DEMO_FALLBACK_MODE:
                raise
            # Phase 18.5 — this is the FIRST LLM call in the whole
            # negotiation graph; if every provider is down and this isn't
            # handled, the demo never even gets as far as propose_offer's
            # own fallback. Default to the safe, well-supported path
            # (offer a discount) rather than guessing at a bundle, since
            # the discount ladder's value is fully deterministic and has
            # its own fallback framing already.
            write_audit_log(
                db,
                order_id=None,
                event_type="llm_fallback_used",
                payload={"session_id": state["session_id"], "error": str(e), "node": "decide_to_offer"},
            )
            decision = DecideToOfferOutput(
                should_offer=True, offer_shape="discount", reasoning="Demo fallback: LLM provider(s) unavailable."
            )

        write_audit_log(
            db,
            order_id=None,
            event_type="offer_decision",
            payload={
                "session_id": state["session_id"],
                "should_offer": decision.should_offer,
                "offer_shape": decision.offer_shape,
                "reasoning": decision.reasoning,
                "attempt_number": state["turn_count"] + 1,
            },
        )

        if decision.should_offer:
            return Command(update={"_offer_shape": decision.offer_shape}, goto="propose_offer")
        return Command(goto="close_negotiation")
    finally:
        db.close()


def _evaluate_and_log(
    db, state: NegotiationState, offer: dict, attempt_number: int, is_fallback: bool = False
) -> dict:
    """Writes an audit row for the call AND the response — approved or
    rejected, every time, not just on the happy path — then does the actual
    HTTP call to the gate. This is the ONLY path in this codebase that can
    produce an approval_token; nothing else in propose_offer is allowed to
    mint one.
    """
    write_audit_log(
        db,
        order_id=None,
        event_type="gate_call",
        payload={
            "session_id": state["session_id"],
            "requested_offer": offer,
            "attempt_number": attempt_number,
            "is_fallback": is_fallback,
        },
    )
    gate_response = gate_client.evaluate(
        session_id=state["session_id"],
        product_id=state["product_id"],
        cart_quantity=state["cart_quantity"],
        original_price=state["original_price"],
        proposed_offer=offer,
        attempt_number=attempt_number,
    )
    write_audit_log(
        db,
        order_id=None,
        event_type="gate_decision",
        payload={
            "session_id": state["session_id"],
            "approved": gate_response.get("approved"),
            "reason": gate_response.get("reason"),
            "max_allowed": gate_response.get("max_allowed"),
            "final_terms": gate_response.get("final_terms"),
            "is_fallback": is_fallback,
        },
    )
    return gate_response


def propose_offer(state: NegotiationState) -> Command[Literal["handle_response", "close_negotiation"]]:
    """Produces a proposal, then gets it evaluated by the policy gate BEFORE
    it's ever shown to the shopper. Never calls /order/create, never
    touches Order rows, never calls Razorpay directly — the gate's
    approval_token minted here is the ONLY thing /order/create will later
    accept to apply a discount.
    """
    db = SessionLocal()
    try:
        product = db.get(Product, state["product_id"])
        cart_summary = _cart_summary(state, product)
        history_summary = _history_summary(state["conversation_history"])
        offer_shape = state.get("_offer_shape", "discount")
        attempt_number = state["turn_count"] + 1

        # Phase 10: for a straight discount, the PERCENTAGE is decided
        # deterministically by the seller's staged ladder (5% -> 10% ->
        # hold), not invented by the LLM each round — the LLM only writes
        # the framing around a number it's given. Bundles are unaffected
        # (out of Part A's scope: a "discount progression," not bundles)
        # and keep the original fully LLM-driven path below.
        ladder_rung = None
        if offer_shape == "discount":
            ladder_rung = discount_ladder.rung_for_attempt(state["product_id"], attempt_number)
            ladder_value = discount_ladder.ladder_total_value(
                state["original_price"], state["cart_quantity"], ladder_rung.discount_pct
            )
            try:
                message_proposal = _call_structured(
                    system=prompts.propose_discount_message_system(),
                    user=prompts.propose_discount_message_user(
                        cart_summary, history_summary, ladder_rung.discount_pct, ladder_value, ladder_rung.is_final_rung
                    ),
                    schema=ProposeDiscountMessageOutput,
                )
                candidate_offer = {
                    "type": "discount",
                    "value": ladder_value,
                    "reasoning": message_proposal.offer_reasoning,
                }
                candidate_message = message_proposal.message
            except StructuredOutputError as e:
                if not settings.DEMO_FALLBACK_MODE:
                    write_audit_log(
                        db,
                        order_id=None,
                        event_type="offer_generation_failed",
                        payload={"session_id": state["session_id"], "error": str(e), "attempt_number": attempt_number},
                    )
                    closing_note = "Sorry, I wasn't able to put together an offer just now."
                    new_history = state["conversation_history"] + [{"role": "assistant", "content": closing_note}]
                    return Command(
                        update={"conversation_history": new_history, "offer_status": "none", "turn_count": attempt_number},
                        goto="close_negotiation",
                    )

                # Phase 18.5 — every LLM provider is down/unreachable (or
                # genuinely produced unparseable output twice), but the
                # demo doesn't have to stop: the discount VALUE was always
                # deterministic (the ladder), only the prose framing was
                # LLM-authored — so a templated message using that same
                # real number keeps the negotiation narrative alive
                # instead of aborting. Logged as its own event type
                # specifically so this is never mistaken for a real
                # LLM-authored message later.
                write_audit_log(
                    db,
                    order_id=None,
                    event_type="llm_fallback_used",
                    payload={
                        "session_id": state["session_id"],
                        "error": str(e),
                        "attempt_number": attempt_number,
                        "ladder_pct": ladder_rung.discount_pct,
                        "ladder_value": ladder_value,
                    },
                )
                candidate_offer = {
                    "type": "discount",
                    "value": ladder_value,
                    "reasoning": "Demo fallback: LLM provider(s) unavailable, templated around the real ladder value.",
                }
                candidate_message = (
                    f"Thanks for your patience — I can offer {ladder_rung.discount_pct:g}% off, bringing your "
                    f"total to ₹{ladder_value / 100:.2f}. Would that work for you?"
                )
        else:
            try:
                proposal = _call_structured(
                    system=prompts.propose_offer_system(),
                    user=prompts.propose_offer_user(cart_summary, history_summary, offer_shape),
                    schema=ProposeOfferOutput,
                )
            except StructuredOutputError as e:
                # Explicit Phase 2 handling: never call the gate with garbage —
                # no parseable offer means there is nothing to evaluate.
                write_audit_log(
                    db,
                    order_id=None,
                    event_type="offer_generation_failed",
                    payload={"session_id": state["session_id"], "error": str(e), "attempt_number": attempt_number},
                )
                closing_note = "Sorry, I wasn't able to put together an offer just now."
                new_history = state["conversation_history"] + [{"role": "assistant", "content": closing_note}]
                return Command(
                    update={"conversation_history": new_history, "offer_status": "none", "turn_count": attempt_number},
                    goto="close_negotiation",
                )

            candidate_offer = {
                "type": proposal.offer_type,
                "value": proposal.offer_value,
                "reasoning": proposal.offer_reasoning,
            }
            candidate_message = proposal.message

        gate_response = _evaluate_and_log(db, state, candidate_offer, attempt_number)

        if not gate_response["approved"] and gate_response.get("max_allowed") is not None:
            # Rejected, but the gate told us the real ceiling — reformulate
            # DETERMINISTICALLY around that number (no second LLM call
            # choosing the figure) and get THAT re-evaluated too, so nothing
            # reaches the shopper without itself having gone through the gate.
            fallback_offer = {
                "type": "discount",
                "value": gate_response["max_allowed"],
                "reasoning": "Adjusted to the merchant's actual policy ceiling.",
            }
            fallback_message = (
                "I can't do quite that much, but the best I'm able to offer right now is a "
                f"total of ₹{gate_response['max_allowed'] / 100:.2f}. Would that work for you?"
            )
            gate_response = _evaluate_and_log(db, state, fallback_offer, attempt_number, is_fallback=True)
            if gate_response["approved"]:
                candidate_offer = fallback_offer
                candidate_message = fallback_message

        if not gate_response["approved"]:
            # No usable ceiling either — end gracefully. The shopper never
            # sees a number the gate didn't approve; the rejection itself
            # is already in the audit log via _evaluate_and_log above.
            closing_note = (
                "I'm not able to offer a discount on this right now, but I'd still love "
                "for you to grab it at the listed price."
            )
            new_history = state["conversation_history"] + [{"role": "assistant", "content": closing_note}]
            return Command(
                update={"conversation_history": new_history, "offer_status": "none", "turn_count": attempt_number},
                goto="close_negotiation",
            )

        proposed_offer: ProposedOffer = candidate_offer

        # Ladder metadata is only attached when the rung that was actually
        # shown to the shopper is still the ladder's own value — if the
        # gate rejected it and the deterministic max_allowed fallback took
        # over instead (see above), that's no longer "ladder rung N", so
        # don't mislabel it as one.
        ladder_fields = {}
        if ladder_rung is not None and proposed_offer.get("value") == ladder_value:
            ladder_fields = {"ladder_pct": ladder_rung.discount_pct, "ladder_is_final_rung": ladder_rung.is_final_rung}

        write_audit_log(
            db,
            order_id=None,
            event_type="offer_proposed",
            payload={
                "session_id": state["session_id"],
                **proposed_offer,
                "message": candidate_message,
                "attempt_number": attempt_number,
                **ladder_fields,
            },
        )

        new_history = state["conversation_history"] + [{"role": "assistant", "content": candidate_message}]

        return Command(
            update={
                "conversation_history": new_history,
                "proposed_offer": proposed_offer,
                "offer_status": "proposed",
                "turn_count": attempt_number,
                "approval_token": gate_response["approval_token"],
            },
            goto="handle_response",
        )
    finally:
        db.close()


def handle_response(
    state: NegotiationState,
) -> Command[Literal["decide_to_offer", "close_negotiation", "handle_response"]]:
    # interrupt() must be the first statement: on resume, this node reruns
    # from the top, and only the code AFTER interrupt() should have
    # side effects (audit writes, etc.) — otherwise a replay would double-write.
    user_message: str = interrupt({"awaiting": "user_reply"})

    db = SessionLocal()
    try:
        product = db.get(Product, state["product_id"])
        cart_summary = _cart_summary(state, product)
        new_history = state["conversation_history"] + [{"role": "user", "content": user_message}]
        history_summary = _history_summary(new_history)
        offer_summary = _offer_summary(state["proposed_offer"])

        interpretation = _call_structured(
            system=prompts.handle_response_system(),
            user=prompts.handle_response_user(cart_summary, history_summary, offer_summary),
            schema=HandleResponseOutput,
        )

        write_audit_log(
            db,
            order_id=None,
            event_type="response_interpreted",
            payload={
                "session_id": state["session_id"],
                "intent": interpretation.intent,
                "user_message": user_message,
                "reasoning": interpretation.reasoning,
            },
        )

        history_with_reply = new_history
        if interpretation.intent in ("off_topic", "accept", "reject"):
            history_with_reply = new_history + [
                {"role": "assistant", "content": interpretation.reply_message}
            ]

        if interpretation.intent == "accept":
            return Command(
                update={"conversation_history": history_with_reply, "offer_status": "accepted"},
                goto="close_negotiation",
            )
        if interpretation.intent == "reject":
            return Command(
                update={"conversation_history": history_with_reply, "offer_status": "rejected"},
                goto="close_negotiation",
            )
        if interpretation.intent == "counter":
            # Loop back to decide_to_offer with the updated history; propose_offer's
            # next message (if any) is what the shopper actually sees next.
            return Command(
                update={"conversation_history": history_with_reply, "offer_status": "countered"},
                goto="decide_to_offer",
            )

        # off_topic — answer, then keep waiting for the shopper's actual decision.
        return Command(update={"conversation_history": history_with_reply}, goto="handle_response")
    finally:
        db.close()


def close_negotiation(state: NegotiationState) -> dict:
    if state["offer_status"] == "accepted":
        closed_reason = "accepted"
    elif state["offer_status"] == "rejected":
        closed_reason = "rejected"
    elif state["turn_count"] >= MAX_OFFER_ATTEMPTS:
        closed_reason = "attempt_cap_reached"
    else:
        closed_reason = "no_offer_made"

    db = SessionLocal()
    try:
        write_audit_log(
            db,
            order_id=None,
            event_type="negotiation_closed",
            payload={
                "session_id": state["session_id"],
                "final_status": state["offer_status"],
                "turns": state["turn_count"],
                "closed_reason": closed_reason,
            },
        )

        # Phase 10, Part B: a SEPARATE, best-effort LLM call, made only
        # after the negotiation's real outcome is already recorded above —
        # this has no path back into decide_to_offer/propose_offer and
        # cannot affect the negotiation itself in any way. Purely
        # presentation-layer enrichment for Priya's dashboard: if it fails
        # for any reason, the session still closes normally with no
        # summary, exactly like Phase 2's StructuredOutputError handling
        # for offer generation.
        try:
            product = db.get(Product, state["product_id"])
            cart_summary = _cart_summary(state, product)
            history_summary = _history_summary(state["conversation_history"])
            mindset = _call_structured(
                system=prompts.customer_mindset_system(),
                user=prompts.customer_mindset_user(cart_summary, history_summary, state["offer_status"], closed_reason),
                schema=CustomerMindsetOutput,
            )
            write_audit_log(
                db,
                order_id=None,
                event_type="customer_mindset_summary",
                payload={"session_id": state["session_id"], "summary": mindset.summary},
            )
        except Exception as e:
            logger.warning("customer_mindset_summary skipped for session %s: %s", state["session_id"], e)

        return {}
    finally:
        db.close()
