"""Phase 20 — production-hardening pass verification.

Covers what's NEW in this pass, complementing (not duplicating) the
existing Phase 17 suite: negotiation/order idempotency, Supabase-token
authentication and server-side role enforcement (never trusting a
frontend-supplied role), buyer-agent order ownership isolation, and
Razorpay webhook event-id deduplication. Same discipline as the rest of
this directory — live services only, real HTTP calls, skip (not silently
pass) if a required service isn't reachable.
"""

import hashlib
import hmac
import json
import time
import uuid

import pytest

from conftest import BACKEND_URL, _load_backend_env_value, get, mint_admin_token, post

# The real RAZORPAY_WEBHOOK_SECRET the running backend is actually
# configured with (backend/.env locally, the process environment in CI),
# rather than a secret hardcoded into this file — the webhook dedup test
# needs to produce a validly-signed payload, the same way a real Razorpay
# delivery would.
WEBHOOK_SECRET = _load_backend_env_value("RAZORPAY_WEBHOOK_SECRET")


# --- Idempotency (Phase 4) ---------------------------------------------


@pytest.mark.usefixtures("require_backend")
def test_negotiate_start_idempotency_key_prevents_duplicate_sessions(evidence):
    """Two POST /negotiate/start calls carrying the SAME Idempotency-Key
    must return the SAME session_id — a retried request (double-click,
    a client that timed out and resent) must never mint a second, live,
    independent negotiation session for the same logical attempt.
    """
    key = f"test-idem-negotiate-{uuid.uuid4()}"
    body = {"product_id": 2, "cart_quantity": 1}

    r1 = post(f"{BACKEND_URL}/negotiate/start", body, headers={"Idempotency-Key": key})
    r2 = post(f"{BACKEND_URL}/negotiate/start", body, headers={"Idempotency-Key": key})
    evidence.record("first_call", status=r1.status_code, session_id=r1.json().get("session_id"))
    evidence.record("second_call", status=r2.status_code, session_id=r2.json().get("session_id"))

    same_session = r1.status_code == 200 and r2.status_code == 200 and r1.json()["session_id"] == r2.json()["session_id"]
    evidence.flush("PASS" if same_session else "FAIL (vulnerable — duplicate session minted)")
    assert same_session, f"Expected identical session_id, got {r1.json().get('session_id')} vs {r2.json().get('session_id')}"


@pytest.mark.usefixtures("require_backend")
def test_order_create_idempotency_key_prevents_duplicate_orders(evidence):
    """Two POST /order/create calls carrying the SAME Idempotency-Key must
    return the SAME razorpay_order_id — never two real Razorpay orders
    for one logical checkout attempt.
    """
    key = f"test-idem-order-{uuid.uuid4()}"
    body = {"product_id": 2, "quantity": 1}

    r1 = post(f"{BACKEND_URL}/order/create", body, headers={"Idempotency-Key": key})
    r2 = post(f"{BACKEND_URL}/order/create", body, headers={"Idempotency-Key": key})
    evidence.record("first_call", status=r1.status_code, order_id=r1.json().get("razorpay_order_id"))
    evidence.record("second_call", status=r2.status_code, order_id=r2.json().get("razorpay_order_id"))

    same_order = r1.status_code == 200 and r2.status_code == 200 and r1.json()["razorpay_order_id"] == r2.json()["razorpay_order_id"]
    evidence.flush("PASS" if same_order else "FAIL (vulnerable — duplicate order created)")
    assert same_order, f"Expected identical razorpay_order_id, got {r1.json().get('razorpay_order_id')} vs {r2.json().get('razorpay_order_id')}"


# --- Authentication / role enforcement (Phase 2) ------------------------


@pytest.mark.usefixtures("require_backend")
def test_dashboard_requires_authentication(evidence):
    """Every /dashboard/* route is merchant-admin-gated — a plain,
    unauthenticated request must be rejected, never silently served.
    """
    resp = get(f"{BACKEND_URL}/dashboard/summary")
    evidence.record("unauthenticated_dashboard_summary", status=resp.status_code, body=resp.json())
    evidence.flush("PASS" if resp.status_code == 401 else f"FAIL (got {resp.status_code}, expected 401)")
    assert resp.status_code == 401


@pytest.mark.usefixtures("require_backend")
def test_product_creation_requires_authentication(evidence):
    """POST /product (catalog administration) must reject an
    unauthenticated request, never silently create a product.
    """
    resp = post(f"{BACKEND_URL}/product", {"name": "Adversarial Test Product", "price": 100, "stock": 1})
    evidence.record("unauthenticated_product_create", status=resp.status_code, body=resp.json())
    evidence.flush("PASS" if resp.status_code == 401 else f"FAIL (got {resp.status_code}, expected 401)")
    assert resp.status_code == 401


@pytest.mark.usefixtures("require_backend")
def test_forged_admin_role_claim_is_rejected(evidence):
    """The exact attack this whole auth model exists to prevent: craft a
    JWT that LOOKS right — correct shape, a claim of
    app_metadata.role = "MERCHANT_ADMIN" — but is signed with an
    attacker-chosen secret, not Supabase's real one. If the backend ever
    trusted the claim without verifying the signature, this would grant
    admin access to anyone who can read this test's source. It must be
    rejected outright.
    """
    import base64

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": "attacker-forged-subject",
                "email": "attacker@example.com",
                "app_metadata": {"role": "MERCHANT_ADMIN"},
                "exp": int(time.time()) + 3600,
            }
        ).encode()
    )
    # Signed with a secret the attacker made up, NOT the real
    # SUPABASE_JWT_SECRET — this is the entire point of the test.
    fake_secret = "attacker-does-not-know-the-real-secret"
    signing_input = f"{header}.{payload}".encode()
    signature = _b64url(hmac.new(fake_secret.encode(), signing_input, hashlib.sha256).digest())
    forged_token = f"{header}.{payload}.{signature}"

    resp = get(f"{BACKEND_URL}/dashboard/summary", headers={"Authorization": f"Bearer {forged_token}"})
    evidence.record("forged_admin_token_request", status=resp.status_code, body=resp.json())
    # 401 (signature verification ran and correctly rejected the forgery)
    # and 503 (no SUPABASE_URL/SUPABASE_JWT_SECRET configured in this
    # environment at all, so require_user() fails closed rather than
    # accepting an unverifiable token) are BOTH safe, correct outcomes —
    # either way, the forged token was never granted access. Only a 200
    # here would be the actual vulnerability this test exists to catch.
    safely_rejected = resp.status_code in (401, 503)
    evidence.flush("PASS" if safely_rejected else f"FAIL — SECURITY BUG: forged admin token was accepted (got {resp.status_code})")
    assert safely_rejected, (
        "SECURITY BUG: a JWT claiming MERCHANT_ADMIN, signed with an attacker-chosen secret, "
        f"was accepted (HTTP {resp.status_code}) instead of being safely rejected."
    )


@pytest.mark.usefixtures("require_backend")
def test_valid_admin_token_is_accepted(evidence):
    """The other half of the auth story the forged-token test above
    doesn't cover: a REAL, validly-signed token for a MERCHANT_ADMIN-
    allowlisted email must actually be accepted and granted access — a
    security-only test suite that only ever proves rejection could hide
    a signature-verification bug that rejects EVERYTHING, valid tokens
    included, and still look "secure." Skipped if this environment has
    no local SUPABASE_JWT_SECRET configured to mint a token with.
    """
    token = mint_admin_token()
    if not token:
        pytest.skip("No local SUPABASE_JWT_SECRET configured — see backend/.env")

    resp = get(f"{BACKEND_URL}/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    evidence.record("valid_admin_token_request", status=resp.status_code)
    evidence.flush("PASS" if resp.status_code == 200 else f"FAIL (got {resp.status_code}, expected 200)")
    assert resp.status_code == 200, f"A validly-signed MERCHANT_ADMIN token was rejected (HTTP {resp.status_code}) — signature verification is likely broken, not just strict."


# --- Buyer-agent order isolation (Phase 7) -------------------------------


@pytest.mark.usefixtures("require_backend")
def test_buyer_agent_cannot_query_an_order_that_is_not_theirs(evidence):
    """A registered, authenticated buyer agent must not be able to read
    another buyer's (or a human shopper's) order by simply guessing/
    incrementing an order ID — ownership must be enforced server-side,
    not left to "well, IDs are hard to guess."
    """
    reg = post(f"{BACKEND_URL}/agent/v1/register", {"buyer_agent_id": f"test-isolation-{uuid.uuid4().hex[:10]}"})
    evidence.record("register_agent", status=reg.status_code, body=reg.json())
    api_key = reg.json()["api_key"]

    # Order 1 predates every buyer-agent registration this test could
    # possibly own — if it exists at all, it is guaranteed not to be
    # this agent's. Either way (not found, or found-but-not-theirs) the
    # correct response is the same: 404, never someone else's order data.
    resp = get(f"{BACKEND_URL}/agent/v1/order/1/status", headers={"Authorization": f"Bearer {api_key}"})
    evidence.record("cross_agent_order_query", status=resp.status_code, body=resp.text)
    evidence.flush("PASS" if resp.status_code == 404 else f"FAIL — SECURITY BUG: got {resp.status_code}, expected 404")
    assert resp.status_code == 404, (
        f"SECURITY BUG: a buyer agent could read order #1's status (HTTP {resp.status_code}) "
        "despite not owning it — ownership isolation is not being enforced."
    )


@pytest.mark.usefixtures("require_backend")
def test_agent_order_status_requires_authentication(evidence):
    resp = get(f"{BACKEND_URL}/agent/v1/order/1/status")
    evidence.record("unauthenticated_order_status", status=resp.status_code)
    evidence.flush("PASS" if resp.status_code == 401 else f"FAIL (got {resp.status_code}, expected 401)")
    assert resp.status_code == 401


# --- Webhook deduplication (Phase 5) -------------------------------------


def _sign_webhook_body(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.skipif(not WEBHOOK_SECRET, reason="RAZORPAY_WEBHOOK_SECRET not found in backend/.env")
@pytest.mark.usefixtures("require_backend")
def test_webhook_duplicate_event_id_is_deduplicated(evidence):
    """A validly-signed webhook payload replayed with the SAME event id
    must be recognized as a duplicate the second time, not reprocessed —
    the exact gap redteam/attacks/replay.py's webhook_replay case found
    open. This proves the specific fix (Phase 5): a unique-constrained
    WebhookEvent.event_id row, checked before any payment-status side
    effect runs.
    """
    event_id = f"evt_test_dedup_{uuid.uuid4().hex}"
    payload = {
        "id": event_id,
        "event": "payment.failed",  # a real, side-effect-bearing event type
        "created_at": int(time.time()),
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_dedup_does_not_need_to_exist",
                    "order_id": "order_test_dedup_does_not_need_to_exist",
                    "status": "failed",
                }
            }
        },
    }
    body = json.dumps(payload).encode()
    signature = _sign_webhook_body(body)
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}

    import requests

    r1 = requests.post(f"{BACKEND_URL}/webhook/razorpay", data=body, headers=headers, timeout=10)
    r2 = requests.post(f"{BACKEND_URL}/webhook/razorpay", data=body, headers=headers, timeout=10)
    evidence.record("first_delivery", status=r1.status_code, body=r1.text)
    evidence.record("replayed_delivery", status=r2.status_code, body=r2.text)

    try:
        second_marked_duplicate = r2.status_code == 200 and r2.json().get("duplicate") is True
    except ValueError:
        second_marked_duplicate = False

    evidence.flush(
        "PASS" if second_marked_duplicate else "FAIL — replayed webhook was not recognized as a duplicate",
    )
    assert second_marked_duplicate, (
        f"Second delivery of the same event_id was not flagged duplicate (status={r2.status_code}, body={r2.text!r})"
    )


@pytest.mark.usefixtures("require_backend")
def test_webhook_stale_event_is_rejected(evidence):
    """A webhook payload whose own `created_at` is far in the past (well
    beyond a reasonable delivery window) must be rejected outright, even
    if its signature is otherwise perfectly valid — the defense against a
    captured, validly-signed payload being replayed long after the fact.
    """
    if not WEBHOOK_SECRET:
        pytest.skip("RAZORPAY_WEBHOOK_SECRET not found in backend/.env")

    event_id = f"evt_test_stale_{uuid.uuid4().hex}"
    payload = {
        "id": event_id,
        "event": "payment.failed",
        "created_at": int(time.time()) - 90000,  # ~25 hours old — past the 24h freshness window
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_stale_does_not_need_to_exist",
                    "order_id": "order_test_stale_does_not_need_to_exist",
                    "status": "failed",
                }
            }
        },
    }
    body = json.dumps(payload).encode()
    signature = _sign_webhook_body(body)
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}

    import requests

    resp = requests.post(f"{BACKEND_URL}/webhook/razorpay", data=body, headers=headers, timeout=10)
    evidence.record("stale_webhook_delivery", status=resp.status_code, body=resp.text)
    evidence.flush("PASS" if resp.status_code == 400 else f"FAIL (got {resp.status_code}, expected 400)")
    assert resp.status_code == 400
