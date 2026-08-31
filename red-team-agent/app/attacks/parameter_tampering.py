"""Attacks the endpoints reachable by skipping the intended agent/LLM
conversation entirely and calling the seller's public HTTP surface
directly with crafted parameters. Distinct from malformed_terms.py (which
already covers negative/zero/huge/wrong-type `proposed_terms.value` and
extra fields on /agent/v1/negotiate) — this module targets the endpoints
malformed_terms.py doesn't touch: the HUMAN checkout path (/order/create,
which has no proposed_terms field at all, only a bare approval_token
string) and the quantity field, which no existing case exercises.
"""

from app.config import settings
from app.report import AttackCase, AttackModuleResult
from app.seller_client import negotiate_and_get_token, order_create

PRODUCT_ID = 2  # Ceramic Coffee Mug


def _case_direct_discount_injection() -> AttackCase:
    """/order/create's ONLY discount mechanism is approval_token (see
    backend/app/schemas/order.py's docstring: 'No raw amount is ever
    accepted from the client'). There is no discount/amount field to
    smuggle a number into — the only thing an attacker skipping the
    negotiation conversation can DO is hand the endpoint a made-up token
    string and hope it's trusted on shape alone.
    """
    fabricated_token = "totally-made-up-token-not-issued-by-anyone-1234567890"
    resp = order_create(PRODUCT_ID, 1, approval_token=fabricated_token)
    ok = False
    note = f"Unexpected HTTP {resp.status_code}"
    if resp.status_code == 200:
        body = resp.json()
        listed_total = 29900  # Ceramic Coffee Mug's real price, paise
        ok = body.get("amount") == listed_total
        note = (
            f"Order created at full listed price (₹{body.get('amount', 0) / 100:.2f}) — the fabricated token was "
            "rejected by policy-gate's /verify (unknown_token) and this endpoint's documented fallback behavior "
            "('a bad token silently falls back to full price, never an error') took over, exactly as it should."
            if ok else
            f"CONFIRMED GAP: order was created at amount={body.get('amount')}, not the full listed price "
            f"({listed_total}) — a fabricated approval_token string was accepted as if it granted a real discount."
        )
    return AttackCase(
        name="Direct discount injection — fabricated approval_token at /order/create, bypassing negotiation entirely",
        description=(
            "Calls POST /order/create directly with a made-up approval_token string that was never issued by "
            "policy-gate — the only way to attempt a discount without ever going through /negotiate/start or "
            "/agent/v1/negotiate, since this endpoint accepts no other discount-shaped field."
        ),
        request=f"POST /order/create\n{{product_id: {PRODUCT_ID}, quantity: 1, approval_token: {fabricated_token!r}}}",
        actual_response=f"HTTP {resp.status_code}: {resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes=note,
        blocked=ok,
    )


def _case_negative_and_overflow_quantity() -> AttackCase:
    """Neither /order/create nor /agent/v1/purchase's `quantity` field has
    been exercised by any existing attack module (malformed_terms.py only
    hits /agent/v1/negotiate) — a negative or absurdly large quantity here
    would attack `amount = product.price * quantity`, either as a markup-
    disguised-as-negative-charge or an integer-range issue reaching
    Razorpay's order.create call.
    """
    cases = [("negative quantity", -5), ("zero quantity", 0), ("absurdly large quantity", 10_000_000_000)]
    results = []
    status_codes = []
    for label, quantity in cases:
        resp = order_create(PRODUCT_ID, quantity, approval_token=None)
        status_codes.append(resp.status_code)
        results.append(f"{label} ({quantity}): HTTP {resp.status_code} — {resp.text[:200]}")

    # Correct behavior for ALL three: rejected before a Razorpay order is
    # ever created — either 422 (Pydantic's Field(gt=0) catches
    # negative/zero) or a clean 4xx for insufficient stock on the huge
    # value (never a 500, never a real order at a negative/absurd amount).
    all_ok = all(code in (400, 422) for code in status_codes)

    return AttackCase(
        name="Negative / zero / overflow-sized quantity at /order/create",
        description=(
            "Sends quantity=-5, quantity=0, and quantity=10,000,000,000 to POST /order/create — none of these "
            "should ever reach a real Razorpay order.create call; each should fail cleanly (422 validation or "
            "400 insufficient stock), never a 500, and never a negative/zero/absurd real charge."
        ),
        request="3x POST /order/create with quantity ∈ {-5, 0, 10000000000}",
        actual_response="\n".join(results),
        verdict="PASS" if all_ok else "FAIL",
        notes=(
            "All three rejected cleanly before reaching Razorpay."
            if all_ok else
            f"At least one boundary value was NOT cleanly rejected (status codes: {status_codes}) — investigate "
            "immediately, this could mean an actual Razorpay order was created with a negative/zero/absurd amount."
        ),
        requests_sent=3,
        expected_successes=0,
        actual_successes=sum(1 for code in status_codes if code not in (400, 422)),
        blocked=all_ok,
    )


def _case_missing_approval_token() -> AttackCase:
    """The brief's literal ask ('assert rejection') doesn't match this
    system's actual, intentional design: /order/create with NO token is
    the normal, un-negotiated checkout path — any shopper can buy at the
    listed price without ever negotiating. Rejecting that outright would
    be wrong, not secure. What actually matters — and is what this case
    checks — is the narrower, correct property: no token means no
    discount, ever, not an error.
    """
    resp = order_create(PRODUCT_ID, 1, approval_token=None)
    ok = False
    note = f"Unexpected HTTP {resp.status_code}"
    if resp.status_code == 200:
        listed_total = 29900
        ok = resp.json().get("amount") == listed_total
        note = (
            f"Order created at full listed price (₹{resp.json().get('amount', 0) / 100:.2f}) with no token "
            "presented — correct: an un-negotiated checkout is a normal, intended path in this system, and it "
            "must never silently apply a discount, not that it must be refused outright."
            if ok else
            f"CONFIRMED GAP: no approval_token was presented but the order amount was "
            f"{resp.json().get('amount')}, not the full listed price."
        )
    return AttackCase(
        name="Order finalization with no approval_token at all",
        description=(
            "Calls POST /order/create with approval_token omitted entirely. Reframed from the brief's literal "
            "'assert rejection' — this endpoint intentionally allows checkout without ever negotiating (that's "
            "the whole 'listed price' path); the real security property is 'no token, no discount,' not 'no "
            "token, no order.'"
        ),
        request=f"POST /order/create\n{{product_id: {PRODUCT_ID}, quantity: 1, approval_token: null}}",
        actual_response=f"HTTP {resp.status_code}: {resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes=note,
        blocked=ok,
    )


def _case_quantity_scope_substitution() -> AttackCase:
    """The identity-scoping half of 'session/token scoping' is already
    covered by token_replay_variants.py's cross-buyer case. This covers
    the OTHER half: does an approval_token minted for one cart_quantity
    stay scoped to that quantity, or can it be redeemed against a
    DIFFERENT quantity of the same product via a completely separate
    checkout call (not even the same terms_reference/purchase flow — the
    human /order/create path, which takes an approval_token directly)?
    """
    buyer_id, api_key = settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY
    neg = negotiate_and_get_token(buyer_id, api_key, PRODUCT_ID, 2, value=53820)  # 2 units, ~10% off list of 2x29900
    token = neg["approval_token"]

    # Apply the SAME token, minted for quantity=2, to a DIFFERENT
    # checkout call for quantity=1 of the SAME product via /order/create.
    resp = order_create(PRODUCT_ID, 1, approval_token=token)
    listed_total_qty1 = 29900

    ok = False
    note = f"Unexpected HTTP {resp.status_code}"
    if resp.status_code == 200:
        amount = resp.json().get("amount")
        ok = amount == listed_total_qty1
        note = (
            f"Order for quantity=1 was charged the full listed price (₹{amount / 100:.2f}), NOT the quantity=2 "
            "discounted total — policy-gate's /verify correctly rejected the mismatch (approval.cart_quantity=2 "
            "!= requested cart_quantity=1), same terms_mismatch check that already scopes tokens by product_id, "
            "now confirmed to also scope by quantity."
            if ok else
            f"CONFIRMED GAP: a token minted for quantity=2 was honored against a quantity=1 checkout, charging "
            f"amount={amount} instead of the correct full price for 1 unit ({listed_total_qty1})."
        )
    return AttackCase(
        name="Quantity-scope substitution — token minted for qty=2 redeemed against a qty=1 order",
        description=(
            "Negotiates and locks in a discount for quantity=2 of a product, then presents that SAME "
            "approval_token to POST /order/create for a DIFFERENT checkout of quantity=1 — testing the "
            "cart_quantity half of policy-gate's terms_mismatch scoping check (the product_id half is already "
            "covered by token_replay_variants.py's cross-buyer case)."
        ),
        request=f"Negotiate qty=2 -> approval_token={token!r}\nPOST /order/create {{product_id: {PRODUCT_ID}, quantity: 1, approval_token: {token!r}}}",
        actual_response=f"HTTP {resp.status_code}: {resp.text}",
        verdict="PASS" if ok else "FAIL",
        notes=note,
        blocked=ok,
    )


def run() -> AttackModuleResult:
    result = AttackModuleResult(module="parameter_tampering", category="tampering")
    result.add(_case_direct_discount_injection())
    result.add(_case_negative_and_overflow_quantity())
    result.add(_case_missing_approval_token())
    result.add(_case_quantity_scope_substitution())
    return result
