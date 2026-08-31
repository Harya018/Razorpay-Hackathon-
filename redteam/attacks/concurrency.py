"""Attack module 11a — concurrency / race conditions.

HTTP-only, own venv, zero imports from backend/policy-gate/red-team-agent
source — same independence discipline this project applies to buyer-agent.
Every shape used here (request bodies, header formats) was taken from
docs/agent-commerce-interface.md and docs/x402-v2-conformance.md, the same
public contract an external attacker would read, not from importing the
implementation. A red-team tool that cheats by reaching into internals
doesn't prove anything about the real attack surface.

Three scenarios, run with asyncio.gather over a shared httpx.AsyncClient
for genuine concurrent HTTP requests (not a sequential loop that only
looks concurrent):

1. discount_ceiling_race — targets the HUMAN negotiation channel
   (POST /negotiate/start, POST /negotiate/message), the only channel with
   a caller-visible session_id and a policy-gate-enforced per-session
   ceiling (the merchant's MAX_ATTEMPTS attempt cap, and each attempt's
   discount floor). 10 concurrent messages hit ONE session, each pushing
   for the maximum discount; the audit trail is the source of truth for
   whether the cap or the floor was ever exceeded, not the response text.

2. approval_token_race — targets the AGENT channel's single-use
   approval_token: negotiate one real discount, mint one terms_reference,
   fire 10 concurrent /agent/v1/pay redemptions of the SAME
   token+terms_reference.

3. same_session_double_negotiation — fires 2 concurrent
   POST /negotiate/start for the identical cart (product_id +
   cart_quantity — the only "same cart" identity this endpoint's request
   shape has, since it takes no client-supplied session/cart id at all).
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Optional

import httpx

from config import settings
from report import AttackResult, write_results

PRODUCT_ID_HUMAN = 1  # Hand-Painted Ceramic Table Vase — 10% max_discount_pct, MAX_ATTEMPTS=3 (from merchant_rules.py, read as public doc)
PRODUCT_ID_AGENT = 2  # Hand-Thrown Stoneware Mug — 15% default cap
MAX_ATTEMPTS = 3  # policy-gate/app/rules/merchant_rules.py's documented cap

N_CEILING_RACE = 10
N_TOKEN_RACE = 10


# --- x402 PAYMENT-SIGNATURE, re-derived from the public doc, not imported ---


def _build_payment_signature(terms_reference: str, approval_token: Optional[str]) -> str:
    """Conformance fix (docs/x402-conformance-diff.md): PaymentPayload
    carries `accepted` (the full PaymentRequirements object), not
    flattened top-level scheme/network fields. Uses a schema-valid
    PLACEHOLDER `accepted` rather than echoing the seller's real
    PAYMENT-REQUIRED — these scenarios test approval_token/terms_reference
    matching and concurrency behavior, not x402 field-echoing fidelity
    (unlike buyer-agent's production client, which always echoes the real
    accepts[0] verbatim).
    """
    payload = {
        "x402Version": 2,
        "accepted": {
            "scheme": "exact",
            "network": "inr-fiat:razorpay-test",
            "amount": "0",
            "asset": "INR",
            "payTo": "unknown",
            "maxTimeoutSeconds": 300,
        },
        "payload": {"custodialReceipt": {"terms_reference": terms_reference, "approval_token": approval_token}},
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


async def _register_attacker(client: httpx.AsyncClient) -> tuple[str, str]:
    buyer_id = f"{settings.ATTACKER_ID_PREFIX}-{uuid.uuid4().hex[:10]}"
    resp = await client.post(f"{settings.SELLER_BASE_URL}/agent/v1/register", json={"buyer_agent_id": buyer_id})
    resp.raise_for_status()
    return buyer_id, resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# --- Scenario 1: discount_ceiling_race ---------------------------------------


async def discount_ceiling_race(client: httpx.AsyncClient) -> AttackResult:
    start_resp = await client.post(
        f"{settings.BACKEND_BASE_URL}/negotiate/start",
        json={"product_id": PRODUCT_ID_HUMAN, "cart_quantity": 1},
    )
    start_resp.raise_for_status()
    session_id = start_resp.json()["session_id"]

    message = "Please give me your absolute maximum possible discount on this right now — your best price."

    async def fire_one():
        return await client.post(
            f"{settings.BACKEND_BASE_URL}/negotiate/message",
            json={"session_id": session_id, "user_message": message},
            timeout=90,
        )

    responses = await asyncio.gather(*[fire_one() for _ in range(N_CEILING_RACE)], return_exceptions=True)
    ok_responses = [r for r in responses if isinstance(r, httpx.Response)]
    status_codes = [r.status_code for r in ok_responses]
    errors = [r for r in responses if not isinstance(r, httpx.Response)]

    audit_resp = await client.get(f"{settings.BACKEND_BASE_URL}/negotiate/{session_id}/audit", timeout=30)
    entries = audit_resp.json() if audit_resp.status_code == 200 else []

    max_attempt_seen = max(
        (e["payload"].get("attempt_number", 0) for e in entries if e["event_type"] == "gate_call"), default=0
    )
    approved_count = sum(
        1 for e in entries if e["event_type"] == "gate_decision" and e["payload"].get("approved") is True
    )

    # The real "policy-gate ceiling in aggregate" for THIS channel is the
    # merchant's attempt cap (policy-gate's MAX_ATTEMPTS=3) — the discount
    # ladder is turn-based, not a flat "N callers can each claim the max"
    # race. Correct behavior under 10-way concurrency: no more than
    # MAX_ATTEMPTS genuine gate approvals ever happen for this ONE
    # session, and the attempt counter never climbs past the cap, no
    # matter how many concurrent messages arrived — i.e. two of the ten
    # concurrent requests must NOT each land a fresh, independent
    # "maximum discount" as if the other nine never happened.
    blocked = max_attempt_seen <= MAX_ATTEMPTS and approved_count <= MAX_ATTEMPTS
    verdict = "PASS" if blocked else "FAIL"

    notes = (
        f"session_id={session_id}. HTTP status codes: {status_codes} ({len(errors)} client-side exceptions: "
        f"{[repr(e) for e in errors]}). Audit trail: max attempt_number reached={max_attempt_seen} "
        f"(cap={MAX_ATTEMPTS}), gate_decision(approved=True) count={approved_count}. "
    )
    if blocked:
        notes += (
            "The attempt cap held under 10-way concurrent pressure on a single session — the per-session "
            "negotiation lock (backend/app/routes/negotiation.py's _lock_for_session, added after an earlier "
            "same-session race was found and fixed) serializes concurrent resumes, and the graph's own "
            "turn_count >= MAX_OFFER_ATTEMPTS check stops any call past the 3rd legitimate attempt from reaching "
            "the gate at all."
        )
    else:
        notes += (
            "CONFIRMED GAP: either the attempt cap or the count of genuinely-approved offers exceeded the "
            "merchant's documented ceiling for a single session under concurrent load."
        )

    return AttackResult(
        attack_id="concurrency.discount_ceiling_race",
        description=(
            f"Fires {N_CEILING_RACE} concurrent POST /negotiate/message calls against ONE human-negotiation "
            "session, each demanding the maximum discount — asserts the session's own attempt cap and "
            "gate-approval count (read from its audit trail, not response text) never exceed the merchant's "
            f"documented ceiling ({MAX_ATTEMPTS} attempts), i.e. no two of the ten each land an independent "
            "'maximum discount' as if the others never happened."
        ),
        requests_sent=N_CEILING_RACE,
        expected_successes=min(N_CEILING_RACE, MAX_ATTEMPTS),
        actual_successes=approved_count,
        blocked=blocked,
        verdict=verdict,
        notes=notes,
    )


# --- Scenario 2: approval_token_race ------------------------------------------


async def approval_token_race(client: httpx.AsyncClient) -> AttackResult:
    buyer_id, api_key = await _register_attacker(client)
    headers = _auth(api_key)

    neg_resp = await client.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/negotiate",
        headers=headers,
        json={
            "product_id": PRODUCT_ID_AGENT,
            "quantity": 1,
            "buyer_agent_id": buyer_id,
            "proposed_terms": {"type": "discount", "value": 26910},  # within product 2's 15% cap
        },
    )
    neg_resp.raise_for_status()
    neg_body = neg_resp.json()
    if not neg_body.get("approved"):
        return AttackResult(
            attack_id="concurrency.approval_token_race",
            description="Setup failure — could not obtain an approved token to attack.",
            requests_sent=0,
            expected_successes=1,
            actual_successes=0,
            blocked=False,
            verdict="FAIL",
            notes=f"Negotiate was not approved, cannot proceed: {neg_body}",
        )
    token = neg_body["approval_token"]

    purchase_resp = await client.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/purchase",
        headers=headers,
        json={"product_id": PRODUCT_ID_AGENT, "quantity": 1, "buyer_agent_id": buyer_id, "approval_token": token},
    )
    terms_reference = purchase_resp.json()["terms_reference"]
    sig_header = _build_payment_signature(terms_reference, token)

    async def fire_one():
        return await client.post(
            f"{settings.SELLER_BASE_URL}/agent/v1/pay",
            headers={**headers, "PAYMENT-SIGNATURE": sig_header},
            json={"terms_reference": terms_reference, "approval_token": token, "buyer_agent_id": buyer_id},
        )

    responses = await asyncio.gather(*[fire_one() for _ in range(N_TOKEN_RACE)], return_exceptions=True)
    ok_responses = [r for r in responses if isinstance(r, httpx.Response)]
    successes = [r for r in ok_responses if r.status_code == 200]
    rejections = [r for r in ok_responses if r.status_code != 200]
    status_codes = [r.status_code for r in ok_responses]

    blocked = len(successes) == 1
    verdict = "PASS" if blocked else "FAIL"

    rejection_reasons = {r.status_code for r in rejections}
    notes = (
        f"terms_reference={terms_reference}. Status codes across {N_TOKEN_RACE} concurrent redemptions: "
        f"{status_codes}. {len(successes)} succeeded (expected exactly 1). Rejections came back as "
        f"{sorted(rejection_reasons)} (this system's single-use credential is terms_reference, backed by "
        "PurchaseIntent.used claimed via an atomic UPDATE ... WHERE used=0 — a loser gets 402 "
        "'unknown_or_already_used_terms_reference' (x402 conformance fix: payment failures use 402, not 404 — "
        "see docs/x402-conformance-diff.md), this codebase's equivalent of 'token already used'; a fresh "
        f"terms_reference never existed here, so this was reused exactly {N_TOKEN_RACE} times as designed to test)."
        if not blocked
        else f"terms_reference={terms_reference}. Exactly 1/{N_TOKEN_RACE} concurrent redemptions succeeded "
        f"(status codes: {status_codes}); the rest were cleanly rejected (this system's equivalent of "
        "'token already used' is a 402 'unknown_or_already_used_terms_reference', backed by an atomic "
        "UPDATE ... WHERE used=0 claim on PurchaseIntent, not a silent duplicate success)."
    )

    return AttackResult(
        attack_id="concurrency.approval_token_race",
        description=(
            f"Obtains one real, single-use approval_token and terms_reference, then fires {N_TOKEN_RACE} "
            "concurrent POST /agent/v1/pay redemptions of the IDENTICAL token+terms_reference — asserts exactly "
            "1 succeeds and the rest are cleanly rejected, not silently duplicated."
        ),
        requests_sent=N_TOKEN_RACE,
        expected_successes=1,
        actual_successes=len(successes),
        blocked=blocked,
        verdict=verdict,
        notes=notes,
    )


# --- Scenario 3: same_session_double_negotiation ------------------------------


async def same_session_double_negotiation(client: httpx.AsyncClient) -> AttackResult:
    body = {"product_id": PRODUCT_ID_HUMAN, "cart_quantity": 1}

    async def fire_one():
        return await client.post(f"{settings.BACKEND_BASE_URL}/negotiate/start", json=body)

    r1, r2 = await asyncio.gather(fire_one(), fire_one())
    session_ids = [r.json().get("session_id") for r in (r1, r2) if r.status_code == 200]
    distinct = len(set(session_ids))

    # NegotiateStartRequest carries no client-supplied cart/session
    # identity at all (only product_id + cart_quantity, which are not
    # unique — a shopper legitimately CAN open two separate negotiations
    # for the same product) — so this endpoint has no natural key to
    # de-duplicate on today. Two concurrent calls WILL mint two distinct
    # session_ids, each with its own live LangGraph state, by design of
    # the current request shape, not as an accidental race in a
    # check-then-write sequence.
    blocked = distinct <= 1
    verdict = "PASS" if blocked else "FAIL"

    notes = (
        f"HTTP {r1.status_code}, {r2.status_code}. session_ids returned: {session_ids} ({distinct} distinct). "
    )
    if blocked:
        notes += "Only one negotiation state was created for this cart."
    else:
        notes += (
            "CONFIRMED: two independent, fully-live negotiation sessions were created for the identical cart "
            "(product_id, cart_quantity) from two concurrent /negotiate/start calls — two divergent negotiation "
            "states for what a shopper would consider one cart. ROOT CAUSE (not a check-then-write race — a "
            "missing idempotency key): NegotiateStartRequest (backend/app/schemas/negotiation.py) has no "
            "client-supplied cart/session identity field at all, only product_id + cart_quantity, which are NOT "
            "unique (a shopper can legitimately open two separate negotiations for the same product on purpose) "
            "— so there is no natural column for a unique constraint or INSERT ... ON CONFLICT DO NOTHING to key "
            "on today; that fix shape doesn't apply as-is. This project's own frontend (frontend/src/hooks/"
            "useCartAbandonment.js) already works around exactly this by holding a module-level "
            "_negotiateStartInFlight guard before ever calling /negotiate/start — but that only protects ONE "
            "browser tab's own call site, not this endpoint against two independent callers (a red-team script, "
            "or two tabs). PROPOSED MINIMAL FIX (not applied here, per this phase's instruction to report "
            "separately from fixing): add an optional client-supplied idempotency key (e.g. `cart_id: str | "
            "None`) to NegotiateStartRequest; when present, look up an existing live session for that key before "
            "minting a new one (INSERT ... ON CONFLICT DO NOTHING against a new unique (cart_id) column would "
            "then apply cleanly). This is a real, if small, API contract change — not a one-line DB constraint on "
            "the CURRENT schema — so it's flagged here as a finding + proposal, not silently patched in this "
            "attack module."
        )

    return AttackResult(
        attack_id="concurrency.same_session_double_negotiation",
        description=(
            "Fires 2 concurrent POST /negotiate/start calls for the identical cart (product_id, cart_quantity) "
            "before either completes — asserts the system doesn't create two divergent negotiation states for "
            "what should be one shopper's cart."
        ),
        requests_sent=2,
        expected_successes=1,
        actual_successes=distinct,
        blocked=blocked,
        verdict=verdict,
        notes=notes,
    )


async def run() -> list[AttackResult]:
    async with httpx.AsyncClient(timeout=30) as client:
        # Scenario 3 first — cheap and independent. Scenarios 1 and 2 each
        # set up and attack their own dedicated session/token, so running
        # them after doesn't interfere with 3's result.
        r3 = await same_session_double_negotiation(client)
        r1 = await discount_ceiling_race(client)
        r2 = await approval_token_race(client)
    return [r1, r2, r3]


def main():
    results = asyncio.run(run())
    for r in results:
        print(f"[{r.verdict}] {r.attack_id} — sent={r.requests_sent} expected={r.expected_successes} actual={r.actual_successes} blocked={r.blocked}")
        print(f"    {r.notes}\n")

    out_path = write_results("concurrency", results)
    print(f"wrote {out_path}")

    failed = sum(1 for r in results if r.verdict == "FAIL")
    print(f"\n=== SUMMARY: {len(results) - failed}/{len(results)} passed, {failed} failed ===")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
