"""Attack module 11b — replay / idempotency.

Same discipline as concurrency.py: HTTP-only, own venv, zero imports from
backend/policy-gate source. The one deliberate exception is
RAZORPAY_WEBHOOK_SECRET (see config.py's comment) — used only to mint the
single "captured" webhook artifact each webhook-facing scenario then
replays unmodified, modeling an attacker who obtained one genuine,
validly-signed delivery (compromised relay, log leak, MITM), not one who
stole the merchant's secret for arbitrary forgery.

Three scenarios:

1. webhook_replay — resend an IDENTICAL, validly-signed payment.captured
   payload (same signature, same event id) 5 times sequentially, 1s apart.
   Expected to FAIL on this codebase: the webhook handler has no
   event_id/payment_id dedup check at all (confirmed by reading
   backend/app/routes/payments.py's razorpay_webhook() — every call
   returns the identical {"status": "ok"}, whether it's the first
   delivery or the fifth), so there is no "duplicate, already processed"
   response distinguishable from a fresh one. Recorded as a finding, not
   a harness bug.

2. stale_signature_replay — waits past any timestamp-based freshness
   window, then replays a validly-signed payload. Razorpay's HMAC
   signature here has no timestamp/nonce component at all (confirmed by
   reading the handler's use of razorpay_client.utility.
   verify_webhook_signature, a pure HMAC-SHA256 over body+secret) — so
   this is expected to FAIL too: an unbounded validity window, noted
   explicitly as its own finding rather than silently engineered around.

3. approval_token_delayed_reuse — a plain (non-concurrent) replay of a
   single-use approval_token 5 seconds after its first, successful
   redemption. Expected to PASS: this is backed by an atomic claim on
   PurchaseIntent.used, not a time-based control, so a delay shouldn't
   matter either way.
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

PRODUCT_ID = 2  # Hand-Thrown Stoneware Mug

_MERCHANT_IMPACT_DEDUP = (
    "MERCHANT IMPACT: this webhook handler currently only ever reassigns order.status and "
    "razorpay_payment_id to the same values on every replay, which happens to be harmless TODAY — but the "
    "handler has no idea it's seeing a duplicate at all. The moment this endpoint grows anything additive "
    "(crediting a loyalty-points balance, sending a confirmation email, decrementing stock a second time, "
    "triggering a fulfillment webhook to a warehouse system), a replayed or duplicate-delivered webhook "
    "(which Razorpay's own docs say to expect — at-least-once delivery, not exactly-once) would double-apply "
    "that effect with no code change needed to trigger it — the gap is already live, just not yet expensive."
)

_MERCHANT_IMPACT_STALE = (
    "MERCHANT IMPACT: because the signature has no timestamp/nonce, ANY validly-signed payload capture — "
    "however it happened (a compromised log aggregator, a webhook relay/proxy breach, a leaked support "
    "ticket with a raw payload pasted into it) — remains replayable indefinitely, not just for a short window "
    "after the original delivery. A merchant's real exposure window for a leaked webhook body is 'forever,' "
    "not 'until Razorpay's own webhook expires,' because the signature that's supposed to gate it never dies."
)


# --- x402 PAYMENT-SIGNATURE, re-derived from the public doc, not imported ---


def _build_payment_signature(terms_reference: str, approval_token: Optional[str]) -> str:
    """Conformance fix (docs/x402-conformance-diff.md): PaymentPayload
    carries `accepted` (the full PaymentRequirements object), not
    flattened top-level scheme/network fields. Uses a schema-valid
    PLACEHOLDER `accepted` rather than echoing the seller's real
    PAYMENT-REQUIRED — these scenarios test replay/idempotency behavior,
    not x402 field-echoing fidelity (unlike buyer-agent's production
    client, which always echoes the real accepts[0] verbatim).
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


def _sign_webhook(body_bytes: bytes) -> str:
    return hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


def _webhook_body(razorpay_order_id: str, event_type: str, payment_id: str, event_id: str) -> bytes:
    """Realistic Razorpay webhook shape, including a top-level event `id`
    (Razorpay's own recommended idempotency key) — included specifically
    so this test can show the handler never looks at it, not because the
    handler needs it to function.
    """
    event = {
        "id": event_id,
        "entity": "event",
        "event": event_type,
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": razorpay_order_id,
                    "status": "captured" if event_type == "payment.captured" else "failed",
                }
            }
        },
        "created_at": int(time.time()),
    }
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


async def _register_attacker(client: httpx.AsyncClient) -> tuple[str, str]:
    buyer_id = f"{settings.ATTACKER_ID_PREFIX}-{uuid.uuid4().hex[:10]}"
    resp = await client.post(f"{settings.SELLER_BASE_URL}/agent/v1/register", json={"buyer_agent_id": buyer_id})
    resp.raise_for_status()
    return buyer_id, resp.json()["api_key"]


async def _buy_at_listed_price(client: httpx.AsyncClient) -> tuple[str, int, str]:
    """Buys one unit of PRODUCT_ID at full price via the agent channel —
    gives us both order_id (for HTTP-only status polling via
    /agent/v1/order/{id}/status) and razorpay_order_id (for the webhook
    payload), without any DB access. Returns (buyer_id, order_id, razorpay_order_id).
    """
    buyer_id, api_key = await _register_attacker(client)
    headers = {"Authorization": f"Bearer {api_key}"}

    purchase_resp = await client.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/purchase",
        headers=headers,
        json={"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id, "approval_token": None},
    )
    terms_reference = purchase_resp.json()["terms_reference"]
    sig_header = _build_payment_signature(terms_reference, None)

    pay_resp = await client.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/pay",
        headers={**headers, "PAYMENT-SIGNATURE": sig_header},
        json={"terms_reference": terms_reference, "approval_token": None, "buyer_agent_id": buyer_id},
    )
    pay_resp.raise_for_status()
    body = pay_resp.json()
    return buyer_id, body["order_id"], body["razorpay_order_id"]


async def _order_status(client: httpx.AsyncClient, order_id: int) -> Optional[str]:
    resp = await client.get(f"{settings.SELLER_BASE_URL}/agent/v1/order/{order_id}/status")
    return resp.json().get("status") if resp.status_code == 200 else None


# --- Scenario 1: webhook_replay ------------------------------------------


async def webhook_replay(client: httpx.AsyncClient) -> AttackResult:
    _, order_id, razorpay_order_id = await _buy_at_listed_price(client)

    payment_id = f"pay_redteamreplay{uuid.uuid4().hex[:14]}"
    event_id = f"evt_redteamreplay{uuid.uuid4().hex[:14]}"
    body = _webhook_body(razorpay_order_id, "payment.captured", payment_id, event_id)
    signature = _sign_webhook(body)

    responses = []
    for i in range(5):
        resp = await client.post(
            f"{settings.BACKEND_BASE_URL}/webhook/razorpay",
            content=body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
        )
        status_after = await _order_status(client, order_id)
        responses.append((resp.status_code, resp.text, status_after))
        if i < 4:
            await asyncio.sleep(1)

    # Correct behavior: call 1's body should differ meaningfully from
    # calls 2-5's (e.g. a "duplicate" flag or a different status code) —
    # never identical bodies that give a caller no way to tell a real
    # first-application from a no-op replay.
    distinct_bodies = {r[1] for r in responses}
    can_distinguish_duplicates = len(distinct_bodies) > 1
    state_stayed_consistent = all(r[2] == "paid" for r in responses)

    blocked = can_distinguish_duplicates
    verdict = "PASS" if blocked else "FAIL"

    notes = (
        f"order_id={order_id}, razorpay_order_id={razorpay_order_id}, event_id={event_id} (present in the "
        f"payload, Razorpay's own recommended idempotency key). 5 sequential replays, 1s apart. Responses: "
        f"{[(sc, txt) for sc, txt, _ in responses]}. order.status after each call: {[s for _, _, s in responses]}. "
    )
    if blocked:
        notes += "Calls 2-5 were distinguishable from call 1's response — a real dedup signal exists."
    else:
        notes += (
            f"CONFIRMED GAP: all 5 responses were byte-identical ({next(iter(distinct_bodies))!r}) — there is no "
            "way for a caller (or Razorpay's own retry logic, or an operator reading logs) to tell the first, "
            "real application of this event from a no-op replay; the handler has no event_id/payment_id "
            f"dedup check at all (confirmed by reading backend/app/routes/payments.py). Order state itself "
            f"{'stayed consistent (paid) across all 5 calls' if state_stayed_consistent else 'DID NOT stay consistent — see per-call status list above, this is worse than the dedup gap alone'} "
            "— harmless today only because every field this handler touches is a plain overwrite to the "
            "identical value, not an increment or a side-effecting action.\n\n" + _MERCHANT_IMPACT_DEDUP
        )

    return AttackResult(
        attack_id="replay.webhook_replay",
        description=(
            "Captures one real, validly-signed payment.captured webhook payload (including a realistic "
            "top-level event id) for a genuine order, then resends the IDENTICAL payload+signature 5 times "
            "sequentially with a 1s gap — asserts only the first call is distinguishable as 'real effect applied' "
            "and calls 2-5 come back recognizable as duplicates, not indistinguishable 200s."
        ),
        requests_sent=5,
        expected_successes=1,
        actual_successes=len(distinct_bodies),
        blocked=blocked,
        verdict=verdict,
        notes=notes,
    )


# --- Scenario 2: stale_signature_replay -----------------------------------


async def stale_signature_replay(client: httpx.AsyncClient) -> AttackResult:
    _, order_id, razorpay_order_id = await _buy_at_listed_price(client)

    payment_id = f"pay_redteamstale{uuid.uuid4().hex[:14]}"
    event_id = f"evt_redteamstale{uuid.uuid4().hex[:14]}"
    body = _webhook_body(razorpay_order_id, "payment.captured", payment_id, event_id)
    signature = _sign_webhook(body)

    wait_seconds = 10
    await asyncio.sleep(wait_seconds)

    resp = await client.post(
        f"{settings.BACKEND_BASE_URL}/webhook/razorpay",
        content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    status_after = await _order_status(client, order_id)

    accepted_despite_age = resp.status_code == 200 and status_after == "paid"
    # A freshness window would REJECT a signature this old with a 4xx. No
    # window at all means it's accepted no matter how old — that
    # acceptance IS the finding here, so "blocked" (attack contained) is
    # false when it's accepted, matching the task's explicit framing that
    # an unbounded window is itself a vulnerability worth recording.
    blocked = not accepted_despite_age
    verdict = "PASS" if blocked else "FAIL"

    notes = (
        f"order_id={order_id}, razorpay_order_id={razorpay_order_id}, event_id={event_id}. Waited {wait_seconds}s "
        f"after signing before sending (any wait demonstrates the same point equally well here — "
        "backend/app/routes/payments.py's razorpay_webhook() calls razorpay_client.utility."
        "verify_webhook_signature(), a pure HMAC-SHA256(body, secret) with no timestamp or nonce component at "
        "all, confirmed by reading the SDK; there is no code path that could reject this on age regardless of "
        f"how long the wait is). Response: HTTP {resp.status_code} {resp.text!r}. order.status after: {status_after!r}. "
    )
    if blocked:
        notes += "Rejected despite a valid signature — a freshness check exists somewhere in this path after all."
    else:
        notes += (
            "CONFIRMED (as expected): the aged-but-validly-signed payload was accepted and applied exactly like "
            "a fresh one — there is no timestamp-based freshness window on this signature at all. Noted "
            "explicitly as a finding per this phase's instruction, not silently engineered around.\n\n"
            + _MERCHANT_IMPACT_STALE
        )

    return AttackResult(
        attack_id="replay.stale_signature_replay",
        description=(
            "Signs a fresh payment.captured payload, waits past any conceivable freshness window, then sends "
            "it — asserts it's rejected on age. If no freshness check exists at all (as reading the handler's "
            "signature-verification code suggests), this is expected to FAIL and is recorded as its own finding: "
            "an unbounded signature validity window."
        ),
        requests_sent=1,
        expected_successes=0,  # expected to be REJECTED — a "success" (200+paid) is the failure mode here
        actual_successes=1 if accepted_despite_age else 0,
        blocked=blocked,
        verdict=verdict,
        notes=notes,
    )


# --- Scenario 3: approval_token_delayed_reuse -----------------------------


async def approval_token_delayed_reuse(client: httpx.AsyncClient) -> AttackResult:
    buyer_id, api_key = await _register_attacker(client)
    headers = {"Authorization": f"Bearer {api_key}"}

    neg_resp = await client.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/negotiate",
        headers=headers,
        json={
            "product_id": PRODUCT_ID,
            "quantity": 1,
            "buyer_agent_id": buyer_id,
            "proposed_terms": {"type": "discount", "value": 26910},  # within product 2's 15% cap
        },
    )
    neg_body = neg_resp.json()
    if not neg_body.get("approved"):
        return AttackResult(
            attack_id="replay.approval_token_delayed_reuse",
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
        json={"product_id": PRODUCT_ID, "quantity": 1, "buyer_agent_id": buyer_id, "approval_token": token},
    )
    terms_reference = purchase_resp.json()["terms_reference"]
    sig_header = _build_payment_signature(terms_reference, token)
    pay_body = {"terms_reference": terms_reference, "approval_token": token, "buyer_agent_id": buyer_id}

    first = await client.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/pay",
        headers={**headers, "PAYMENT-SIGNATURE": sig_header},
        json=pay_body,
    )

    wait_seconds = 5
    await asyncio.sleep(wait_seconds)

    second = await client.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/pay",
        headers={**headers, "PAYMENT-SIGNATURE": sig_header},
        json=pay_body,
    )

    blocked = first.status_code == 200 and second.status_code != 200
    verdict = "PASS" if blocked else "FAIL"

    notes = (
        f"terms_reference={terms_reference}. First redemption: HTTP {first.status_code}. Waited {wait_seconds}s. "
        f"Second redemption (same token+terms_reference): HTTP {second.status_code} {second.text!r}. "
    )
    if blocked:
        notes += (
            "First succeeded, delayed second was rejected — the same atomic claim on PurchaseIntent.used that "
            "holds under concurrency (see concurrency.py's approval_token_race) also holds for a plain, "
            "non-concurrent replay after a real delay."
        )
    else:
        notes += (
            "CONFIRMED GAP: a used single-use token was successfully redeemed a second time after a delay — a "
            "real double-spend.\n\nMERCHANT IMPACT: a single negotiated discount would have been applied to two "
            "separate orders, meaning the merchant charged less than intended for goods actually shipped twice — "
            "direct, measurable revenue loss on every occurrence, not just a theoretical gap."
        )

    return AttackResult(
        attack_id="replay.approval_token_delayed_reuse",
        description=(
            "Redeems a single-use approval_token successfully once, waits 5 seconds (well outside any "
            "concurrency race window), then attempts to redeem the SAME token again — a plain replay, not a "
            "concurrency attack."
        ),
        requests_sent=2,
        expected_successes=1,
        actual_successes=sum(1 for r in (first, second) if r.status_code == 200),
        blocked=blocked,
        verdict=verdict,
        notes=notes,
    )


async def run() -> list[AttackResult]:
    async with httpx.AsyncClient(timeout=30) as client:
        r1 = await webhook_replay(client)
        r2 = await stale_signature_replay(client)
        r3 = await approval_token_delayed_reuse(client)
    return [r1, r2, r3]


def main():
    results = asyncio.run(run())
    for r in results:
        print(f"[{r.verdict}] {r.attack_id} — sent={r.requests_sent} expected={r.expected_successes} actual={r.actual_successes} blocked={r.blocked}")
        print(f"    {r.notes}\n")

    out_path = write_results("replay", results)
    print(f"wrote {out_path}")

    failed = sum(1 for r in results if r.verdict == "FAIL")
    print(f"\n=== SUMMARY: {len(results) - failed}/{len(results)} passed, {failed} failed ===")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
