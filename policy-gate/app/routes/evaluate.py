import hashlib
import os
import secrets
import time
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.approval import Approval
from app.rules import merchant_rules

router = APIRouter()

# WHAT_BROKE.md #9 — a short timeout so a hung/unreachable backend fails
# an /evaluate call fast rather than hanging every negotiation turn. Fail
# CLOSED on any failure (timeout, connection error, 404, malformed body):
# this is the one field the whole gate's trust boundary depends on, so a
# network hiccup must never silently fall back to trusting the caller.
_PRICE_CHECK_TIMEOUT_SECONDS = 3.0


def _fetch_real_unit_price(product_id: int) -> Optional[int]:
    """The independent re-validation this endpoint never had: look up
    what the product actually costs, from the one system that knows —
    the backend's own catalog — instead of trusting whatever original_price
    a caller of this public, unauthenticated endpoint claims. Returns None
    on ANY failure (unreachable backend, unknown product, bad response) —
    callers must treat None as "could not verify," never as "assume OK."
    """
    try:
        resp = httpx.get(f"{settings.BACKEND_URL}/product/{product_id}", timeout=_PRICE_CHECK_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return None
        price = resp.json().get("price")
        return price if isinstance(price, int) else None
    except httpx.HTTPError:
        return None

# Phase 17 trust-boundary test hooks — same pattern as buyer-agent's own
# `force_aggressive_negotiation` test-mode flag: gated behind an env var
# that is never set in normal operation, AND a magic session_id prefix no
# real caller would ever send, so this has zero effect on real traffic.
# Used to reliably create the "killed mid-request" timing windows
# tests/phase17_trust_boundary/test_17_2_gate_kill_midflight.py needs —
# real SIGKILL timing against sub-millisecond in-process work is not
# reproducible without a hook like this.
_TEST_HOOKS_ENABLED = os.getenv("POLICY_GATE_TEST_HOOKS") == "1"
_DELAY_BEFORE_PROCESSING_PREFIX = "phase17-delay-before-processing"
_DELAY_AFTER_COMMIT_PREFIX = "phase17-delay-after-commit"
_TEST_HOOK_DELAY_SECONDS = 8


class ProposedOfferIn(BaseModel):
    type: Literal["discount", "bundle", "none"]
    value: Optional[int] = None
    reasoning: str


class EvaluateRequest(BaseModel):
    session_id: str
    product_id: int
    cart_quantity: int
    original_price: int  # paise, per unit
    proposed_offer: ProposedOfferIn
    attempt_number: int
    # Optional caller identity (Phase 8) — set for the agent-to-agent
    # channel (buyer_agent_id), left unset for human negotiation, which
    # has no buyer identity concept. See Approval.requester_id.
    requester_id: Optional[str] = None


class EvaluateResponse(BaseModel):
    approved: bool
    reason: Optional[str] = None
    max_allowed: Optional[int] = None  # paise, total cart price — the best the merchant would accept, if any
    approval_token: Optional[str] = None
    final_terms: Optional[dict] = None


class VerifyRequest(BaseModel):
    approval_token: str
    product_id: int
    cart_quantity: int
    # Must match the Approval's own requester_id if one was recorded at
    # negotiation time — see Approval.requester_id and _record_and_respond.
    requester_id: Optional[str] = None
    # Red-team-confirmed gap (redteam's tampering.py, "session_id_substitution"):
    # a human-negotiated approval_token had NO binding to the session that
    # earned it at all — any caller presenting the right product_id/
    # cart_quantity could redeem someone else's negotiated discount.
    # Opt-in enforcement, same rollout shape as requester_id but mirrored:
    # requester_id is checked only when the APPROVAL side is non-null
    # (agent channel); session_id is checked only when the REQUEST side
    # is non-null, since callers that don't send it (not yet updated, or
    # the agent channel, which has no session_id concept) see zero
    # behavior change.
    session_id: Optional[str] = None


class VerifyResponse(BaseModel):
    valid: bool
    reason: Optional[str] = None
    final_amount: Optional[int] = None
    session_id: Optional[str] = None


def _generate_token(session_id: str, product_id: int, cart_quantity: int, final_amount: int) -> str:
    nonce = secrets.token_hex(16)
    return hashlib.sha256(
        f"{session_id}|{product_id}|{cart_quantity}|{final_amount}|{nonce}|{settings.GATE_SECRET}".encode("utf-8")
    ).hexdigest()


def _record_and_respond(
    db: Session,
    req: EvaluateRequest,
    decision: str,
    reason: Optional[str] = None,
    max_allowed: Optional[int] = None,
    final_amount: Optional[int] = None,
) -> EvaluateResponse:
    token = None
    if decision == "approved":
        token = _generate_token(req.session_id, req.product_id, req.cart_quantity, final_amount)

    approval = Approval(
        session_id=req.session_id,
        requester_id=req.requester_id,
        product_id=req.product_id,
        cart_quantity=req.cart_quantity,
        decision=decision,
        reason=reason,
        final_amount=final_amount,
        approval_token=token,
        used=False,
    )
    db.add(approval)
    db.commit()

    if _TEST_HOOKS_ENABLED and req.session_id and req.session_id.startswith(_DELAY_AFTER_COMMIT_PREFIX):
        # The decision is already durably committed to Policy Gate's OWN
        # DB at this point — this window simulates the process dying
        # AFTER deciding but BEFORE the caller ever receives that
        # decision, to test for an "orphaned approval" (see test_17_2).
        time.sleep(_TEST_HOOK_DELAY_SECONDS)

    if decision == "approved":
        return EvaluateResponse(
            approved=True,
            approval_token=token,
            final_terms={"type": req.proposed_offer.type, "value": final_amount},
        )
    return EvaluateResponse(approved=False, reason=reason, max_allowed=max_allowed)


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest, db: Session = Depends(get_db)):
    # Deterministic, re-derivable from merchant_rules.py alone — no LLM
    # call anywhere in this service, no trusting a number the agent hands us.

    if _TEST_HOOKS_ENABLED and req.session_id and req.session_id.startswith(_DELAY_BEFORE_PROCESSING_PREFIX):
        # Simulates "request received, but the process dies before doing
        # any work at all" — see test_17_2's kill-during-this-window case.
        time.sleep(_TEST_HOOK_DELAY_SECONDS)

    if req.attempt_number > merchant_rules.MAX_ATTEMPTS:
        return _record_and_respond(db, req, "rejected", reason="attempt_cap_exceeded")

    # WHAT_BROKE.md #9 fix: the caller's original_price is no longer taken
    # on faith. Every REAL caller (backend's own negotiation/agent-commerce
    # routes) already sends product.price fetched fresh from its own DB —
    # this is a no-op for all legitimate traffic and only ever rejects a
    # caller lying about what something costs, live-exploited pre-fix by
    # tests/phase17_trust_boundary/test_17_3_price_tampering.py.
    real_unit_price = _fetch_real_unit_price(req.product_id)
    if real_unit_price is None:
        return _record_and_respond(db, req, "rejected", reason="price_verification_unavailable")
    if req.original_price != real_unit_price:
        return _record_and_respond(db, req, "rejected", reason="original_price_mismatch")

    total_original = req.original_price * req.cart_quantity
    min_unit_price = merchant_rules.min_allowed_unit_price(req.product_id, req.original_price)
    min_total_allowed = min_unit_price * req.cart_quantity

    offer = req.proposed_offer

    if offer.type == "none":
        return _record_and_respond(db, req, "rejected", reason="no_offer_to_evaluate")

    if offer.type == "discount":
        if offer.value is None:
            return _record_and_respond(db, req, "rejected", reason="missing_discount_value")
        if offer.value > total_original:
            return _record_and_respond(db, req, "rejected", reason="discount_value_exceeds_original_price")
        if offer.value < min_total_allowed:
            return _record_and_respond(
                db, req, "rejected", reason="below_floor_or_exceeds_max_discount", max_allowed=min_total_allowed
            )
        return _record_and_respond(db, req, "approved", final_amount=offer.value)

    if offer.type == "bundle":
        # A bundle with no priced terms can't be checked against a floor —
        # rather than wave it through unchecked, treat "unpriced" as
        # "un-evaluatable," which means "not approved."
        if offer.value is None:
            return _record_and_respond(db, req, "rejected", reason="bundle_has_no_priced_terms_to_evaluate")
        if offer.value < min_total_allowed:
            return _record_and_respond(
                db, req, "rejected", reason="bundle_effective_price_below_floor", max_allowed=min_total_allowed
            )
        return _record_and_respond(db, req, "approved", final_amount=offer.value)

    return _record_and_respond(db, req, "rejected", reason="unknown_offer_type")


@router.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest, db: Session = Depends(get_db)):
    approval = db.query(Approval).filter(Approval.approval_token == req.approval_token).first()

    if approval is None:
        return VerifyResponse(valid=False, reason="unknown_token")
    if approval.decision != "approved":
        return VerifyResponse(valid=False, reason="token_not_approved")
    if approval.product_id != req.product_id or approval.cart_quantity != req.cart_quantity:
        return VerifyResponse(valid=False, reason="terms_mismatch")
    # Phase 8 fix: if this approval was granted to a specific identity,
    # only that identity may redeem it. approval.requester_id is NULL for
    # every human-negotiation approval (no buyer identity exists there),
    # so this never changes behavior for the human channel — it only
    # closes the cross-buyer token-theft gap on the agent channel, where
    # buyer_agent_id is always known. See red-team-agent's
    # token_replay_variants report for the original finding.
    if approval.requester_id is not None and approval.requester_id != req.requester_id:
        return VerifyResponse(valid=False, reason="requester_mismatch")
    # Session-scoping fix (see VerifyRequest.session_id's comment): only
    # enforced when the CALLER supplies a session_id, so this is a pure
    # addition for any caller that opts in, and a no-op for any that
    # haven't been updated yet.
    if req.session_id is not None and approval.session_id != req.session_id:
        return VerifyResponse(valid=False, reason="session_mismatch")

    # Phase 8 fix: claim `used` via a single atomic UPDATE ... WHERE
    # used = 0, not the read-then-write this used to be (`if approval.used:
    # ...; approval.used = True; db.commit()`). That read-then-write was a
    # genuine, red-team-confirmed TOCTOU race — two concurrent /verify
    # calls for the SAME approval_token could both read used=False before
    # either committed, honoring one negotiated discount on two separate
    # orders (see /red-team-agent/results/red_team_report.md,
    # concurrent_race Experiment B, which reproduced this live with real
    # concurrent requests and two real Razorpay test-mode orders both
    # getting the discount). The UPDATE's WHERE clause makes the
    # check-and-set a single atomic database operation — only one
    # concurrent caller can ever be the one whose UPDATE actually matches
    # a row, no matter how many arrive at the same instant.
    claimed = db.query(Approval).filter(Approval.id == approval.id, Approval.used.is_(False)).update({"used": True})
    db.commit()
    if claimed == 0:
        return VerifyResponse(valid=False, reason="token_already_used")

    return VerifyResponse(valid=True, final_amount=approval.final_amount, session_id=approval.session_id)
