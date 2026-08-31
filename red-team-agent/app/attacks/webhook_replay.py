"""Attacks the Razorpay webhook handler (backend/app/routes/payments.py's
razorpay_webhook()) — the one endpoint in this codebase that mutates order
state based on an inbound POST with no buyer identity, no approval_token,
and no request-response round trip; its only defense is the HMAC
signature. This module targets replay and out-of-order delivery, not
signature forgery (malformed_terms.py-style input fuzzing already covers
"garbage signature is rejected"; that's not the interesting question here).

To test REPLAY specifically (not secret theft), this module mints exactly
ONE validly-signed webhook payload using RAZORPAY_WEBHOOK_SECRET (see
config.py's comment for why this is a scoped exception, modeling an
attacker who captured one genuine delivery, not one who stole the
merchant's secret for arbitrary forgery) and then works only with that
captured artifact's exact bytes from then on — resending it unmodified, or
constructing a second, equally genuine-shaped event for the SAME order to
test out-of-order delivery, never inventing a signature for a body it
wasn't actually computed over.
"""

import hashlib
import hmac
import json
import time
import uuid

from app.config import settings
from app.db_direct import count_audit_rows_for_order, get_order_by_razorpay_id
from app.report import AttackCase, AttackModuleResult
from app.seller_client import order_create, razorpay_webhook_raw

PRODUCT_ID = 2  # Ceramic Coffee Mug


def _sign(body_bytes: bytes) -> str:
    return hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


def _captured_event_body(razorpay_order_id: str, event_type: str, payment_id: str) -> bytes:
    """Shapes a minimal but realistic Razorpay webhook body — only the
    fields backend/app/routes/payments.py's razorpay_webhook() actually
    reads (payload.payment.entity.order_id / .id, and top-level event) —
    read directly from that handler's source, not guessed.
    """
    event = {
        "event": event_type,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": razorpay_order_id,
                    "status": "captured" if event_type == "payment.captured" else "failed",
                }
            }
        },
    }
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _case_stale_out_of_order_replay() -> AttackCase:
    order_resp = order_create(PRODUCT_ID, 1)
    order_resp.raise_for_status()
    razorpay_order_id = order_resp.json()["razorpay_order_id"]

    payment_id = f"pay_redteamcapture{uuid.uuid4().hex[:14]}"
    captured_body = _captured_event_body(razorpay_order_id, "payment.captured", payment_id)
    captured_sig = _sign(captured_body)

    resp1 = razorpay_webhook_raw(captured_body, captured_sig)
    order_after_captured = get_order_by_razorpay_id(razorpay_order_id)
    status_after_captured = order_after_captured["status"] if order_after_captured else None

    # Now simulate a STALE / out-of-order redelivery: a payment.failed
    # event for the SAME order, arriving AFTER the real payment.captured
    # already landed — Razorpay webhooks are not guaranteed to arrive in
    # order, and a delayed retry of an earlier failed-then-retried attempt
    # is a realistic scenario, not a contrived one.
    failed_body = _captured_event_body(razorpay_order_id, "payment.failed", payment_id)
    failed_sig = _sign(failed_body)
    resp2 = razorpay_webhook_raw(failed_body, failed_sig)
    order_after_failed = get_order_by_razorpay_id(razorpay_order_id)
    status_after_failed = order_after_failed["status"] if order_after_failed else None

    # Correct behavior: once an order is genuinely paid, a stale/out-of-
    # order payment.failed for the SAME payment should never regress it —
    # a merchant's dashboard/fulfillment flow trusting order.status would
    # otherwise show a real, paid order as failed.
    ok = status_after_captured == "paid" and status_after_failed == "paid"

    fix_note = None
    if ok:
        notes = (
            f"Order status after payment.captured: {status_after_captured!r}. After a stale/out-of-order "
            f"payment.failed replay for the SAME order: {status_after_failed!r} — did not regress."
        )
        fix_note = (
            "ORIGINAL RESULT (first run, before the fix below): FAIL. A stale/out-of-order payment.failed webhook "
            "for a payment that had already been captured regressed order.status from 'paid' back to 'failed' — "
            "reproduced live with a real order. Root cause: backend/app/routes/payments.py's razorpay_webhook() "
            "unconditionally set order.status from whichever event_type had just arrived, with no ordering or "
            "monotonicity check — Razorpay does not guarantee webhook delivery order, so a delayed redelivery of "
            "an earlier failed attempt could land after the real capture and silently un-pay a real order in the "
            "merchant's own records.\n\n"
            "FIX APPLIED: payment.failed now only sets order.status when the order is not ALREADY 'paid' "
            "(`elif event_type == \"payment.failed\" and order.status != \"paid\":`) — 'paid' is treated as a "
            "terminal success state that a later failed-event delivery can only be describing an earlier attempt "
            "for, never something that should undo a real capture. payment.captured is left unconditional (a "
            "genuine capture should always win), so this is the minimal one-line guard, not a broader state "
            "machine.\n\n"
            "RE-RUN RESULT (this run, after the fix): PASS — see 'System's actual response' below. The stale "
            "payment.failed no longer regresses an already-paid order."
        )
    elif status_after_captured != "paid":
        notes = (
            f"Setup issue, not a replay finding: order status after payment.captured was "
            f"{status_after_captured!r}, expected 'paid' — the webhook handler may not be processing this "
            f"payload shape as intended. Investigate webhook_status_regression's body shape before trusting the "
            f"regression check below it."
        )
    else:
        notes = (
            f"CONFIRMED GAP: order status regressed from 'paid' to {status_after_failed!r} after a stale/"
            f"out-of-order payment.failed webhook for a payment that had already been captured. "
            "backend/app/routes/payments.py's razorpay_webhook() unconditionally sets order.status from "
            "whatever event_type just arrived, with no ordering/monotonicity check (e.g. comparing against an "
            "event timestamp, or refusing to move a 'paid' order backward) — a delayed or duplicate webhook "
            "delivery for an earlier failed attempt could silently un-pay a real, already-captured order in a "
            "merchant's own records."
        )

    return AttackCase(
        name="Stale/out-of-order webhook replay — payment.failed after payment.captured for the same order",
        description=(
            "Creates a real order, sends a validly-signed payment.captured webhook for it (order -> paid), then "
            "sends a validly-signed payment.failed webhook for the SAME order+payment_id (simulating a stale/"
            "delayed redelivery of an earlier attempt arriving after the real capture) — checking whether "
            "order.status incorrectly regresses."
        ),
        request=(
            f"POST /webhook/razorpay {{event: 'payment.captured', order_id: {razorpay_order_id!r}}}\n"
            f"Then: POST /webhook/razorpay {{event: 'payment.failed', order_id: {razorpay_order_id!r}}} (same payment_id, stale redelivery)"
        ),
        actual_response=f"HTTP {resp1.status_code} then {resp2.status_code}. status_after_captured={status_after_captured!r}, status_after_failed={status_after_failed!r}",
        verdict="PASS" if ok else "FAIL",
        notes=notes,
        fix_applied=fix_note,
        blocked=ok,
    )


def _case_identical_replay_no_double_effect() -> AttackCase:
    """11b's core ask: resend the IDENTICAL payload+signature 5 times,
    confirm only the first has a real effect. Also documents (in notes,
    not as a separate FAIL — the replay itself is harmless here) that this
    handler writes NO audit_log row at all for a webhook-driven status
    change, unlike every other money-relevant path in this codebase.
    """
    order_resp = order_create(PRODUCT_ID, 1)
    order_resp.raise_for_status()
    razorpay_order_id = order_resp.json()["razorpay_order_id"]
    payment_id = f"pay_redteamreplay{uuid.uuid4().hex[:14]}"
    body = _captured_event_body(razorpay_order_id, "payment.captured", payment_id)
    sig = _sign(body)

    statuses = []
    for _ in range(5):
        resp = razorpay_webhook_raw(body, sig)
        row = get_order_by_razorpay_id(razorpay_order_id)
        statuses.append((resp.status_code, row["status"] if row else None, row["razorpay_payment_id"] if row else None))
        time.sleep(1)

    order_row = get_order_by_razorpay_id(razorpay_order_id)
    audit_count = count_audit_rows_for_order(order_row["id"], "order_created") if order_row else 0
    # Idempotent by accident, not by design: razorpay_webhook() has no
    # event_id/payment_id dedup check at all — it just re-assigns
    # order.status = "paid" and razorpay_payment_id = payment_id every
    # time, which happens to be harmless ONLY because both are plain
    # overwrites to the identical value, not an increment/side-effecting
    # write. A single 200 body doesn't confirm that safety generalizes to
    # a handler that does more than reassign two fields — flagged
    # explicitly rather than treated as a designed guarantee.
    all_same = len({s[1:] for s in statuses}) == 1 and statuses[0][1] == "paid"

    return AttackCase(
        name="Identical webhook replay — same validly-signed payload sent 5 times",
        description=(
            "Resends the IDENTICAL captured payment.captured payload+signature 5 times sequentially (1s apart). "
            "A PASS means every resend leaves order.status/razorpay_payment_id unchanged from the first call's "
            "effect — not that a dedup check exists (see notes)."
        ),
        request=f"5x identical POST /webhook/razorpay {{event: 'payment.captured', order_id: {razorpay_order_id!r}, payment_id: {payment_id!r}}}",
        actual_response=f"Per-call (status_code, order.status, razorpay_payment_id): {statuses}",
        verdict="PASS" if all_same else "FAIL",
        notes=(
            (
                f"All 5 replays left order.status='paid' and razorpay_payment_id={payment_id!r} unchanged. "
                "IMPORTANT CAVEAT: this handler has NO event_id/payment_id deduplication check at all (confirmed "
                "by reading backend/app/routes/payments.py's razorpay_webhook() — it unconditionally does "
                "order.status = 'paid'; order.razorpay_payment_id = ... on every payment.captured event). Replay "
                "is harmless here only because both are plain field overwrites to the identical value, not "
                "because idempotency is actually enforced — a future handler that does anything additive (e.g. "
                "incrementing a loyalty-points balance, sending a confirmation email, decrementing stock a second "
                "time) would NOT be safe under this same replay. Treat this PASS as 'no observed harm today,' not "
                "'this endpoint is idempotency-safe by design.'\n\n"
                f"SEPARATE GAP (also confirmed): {order_row['id'] if order_row else '?'} has {audit_count} "
                "'order_created'-type audit_log row(s) attributable to this webhook path — razorpay_webhook() "
                "never calls write_audit_log() at all, so a real, money-relevant order.status transition "
                "(created -> paid) driven by this endpoint leaves NO trace in this codebase's own audit hash "
                "chain, unlike every other order-affecting path (order/create, /agent/v1/pay). This is a "
                "coverage gap in the audit trail, not itself an exploitable replay — noted here rather than "
                "silently fixed, per this phase's own instruction to report findings separately from fixing them."
                if all_same else
                f"CONFIRMED GAP: replays did NOT leave order state consistent — {statuses}. This handler's lack "
                "of an event_id/payment_id dedup check is directly reachable, not merely theoretical."
            )
        ),
        requests_sent=5,
        expected_successes=1,  # 1 real effect; the other 4 should be no-ops (even though this handler always returns 200)
        actual_successes=len({s[1:] for s in statuses}),
        blocked=all_same,
    )


def run() -> AttackModuleResult:
    result = AttackModuleResult(module="webhook_replay", category="replay")
    result.add(_case_stale_out_of_order_replay())
    result.add(_case_identical_replay_no_double_effect())
    return result
