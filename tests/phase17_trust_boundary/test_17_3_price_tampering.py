"""17.3 — Price-tampering re-validation.

Goal (as specified): prove Policy Gate re-validates cart price/contents,
not just discount percentage.

REAL RESULT: it does not. Policy Gate's /evaluate takes the caller's
`original_price` field at face value and only ever checks the PROPOSED
DISCOUNT as a percentage OF THAT CLAIMED NUMBER
(merchant_rules.min_allowed_unit_price(product_id, original_price) —
see policy-gate/app/rules/merchant_rules.py). It has no product catalog
of its own to cross-check against. In the NORMAL application flow this
is masked because the only caller of /evaluate is the backend itself,
which always supplies product.price freshly fetched from its own DB
(see agent_commerce.py's agent_negotiate: `original_price=product.price`).
But /evaluate is a public HTTP endpoint on its own port with NO caller
authentication — anyone who can reach port 8001 directly can supply a
fabricated original_price and have it treated as authoritative.

This test proves the full, unmitigated, end-to-end exploit: fabricate a
low original_price directly against Policy Gate, get a REAL approval
token, and redeem it through the REAL backend's /order/create for a REAL
(test-mode) Razorpay order at a fraction of the product's actual price.
See WHAT_BROKE.md for the full writeup — this is a genuine, critical
finding, not a theoretical one.
"""

import json

import pytest

from conftest import BACKEND_URL, POLICY_GATE_URL, get, post


@pytest.mark.usefixtures("require_policy_gate")
def test_fabricated_original_price_produces_valid_approval_token(evidence):
    """Bypass the backend entirely and call Policy Gate's own /evaluate
    directly with a fabricated (low) original_price. If Policy Gate
    re-validated price independently, this would be rejected. It is not.
    """
    real_product = get(f"{BACKEND_URL}/product/1").json()
    real_price = real_product["price"]
    evidence.record("fetch_real_price", product_id=1, real_price_paise=real_price, product_name=real_product["name"])

    fake_price = 10000  # Rs 100.00 — attacker's claim, vs. the real Rs 2499.00
    fake_discounted_value = 9000  # a "legitimate-looking" 10% off the FAKE price

    resp = post(
        f"{POLICY_GATE_URL}/evaluate",
        {
            "session_id": "phase17-price-tamper-test-1",
            "product_id": 1,
            "cart_quantity": 1,
            "original_price": fake_price,
            "proposed_offer": {"type": "discount", "value": fake_discounted_value, "reasoning": "test"},
            "attempt_number": 1,
        },
    )
    body = resp.json()
    evidence.record(
        "evaluate_with_fabricated_price",
        request={"original_price": fake_price, "proposed_value": fake_discounted_value, "real_price": real_price},
        status_code=resp.status_code,
        response=body,
    )

    verdict = "FAIL (vulnerable)" if body.get("approved") else "PASS (rejected fabricated price)"
    evidence.flush(
        verdict,
        notes="Policy Gate approved a discount computed against a caller-supplied price with no independent "
        "re-validation against the real product catalog." if body.get("approved") else "",
    )

    assert body.get("approved") is False, (
        "SECURITY BUG: Policy Gate approved a discount computed against a fabricated original_price "
        f"({fake_price} paise) instead of the real listed price ({real_price} paise), with no independent "
        "price re-validation. It issued a real approval_token: " + json.dumps(body)
    )


@pytest.mark.usefixtures("require_policy_gate")
def test_fabricated_price_token_redeems_for_a_real_undervalued_order(evidence):
    """The full exploit chain: fabricate a price against Policy Gate directly,
    then redeem the resulting token through the REAL backend checkout path
    (/order/create) — the same endpoint a real shopper's browser calls —
    and confirm whether a real (test-mode) Razorpay order gets created at
    the fraudulent amount.
    """
    real_product = get(f"{BACKEND_URL}/product/1").json()
    real_price = real_product["price"]

    fake_price = 10000
    fake_discounted_value = 9000

    eval_resp = post(
        f"{POLICY_GATE_URL}/evaluate",
        {
            "session_id": "phase17-price-tamper-test-2",
            "product_id": 1,
            "cart_quantity": 1,
            "original_price": fake_price,
            "proposed_offer": {"type": "discount", "value": fake_discounted_value, "reasoning": "test"},
            "attempt_number": 1,
        },
    ).json()
    evidence.record("evaluate_with_fabricated_price", response=eval_resp)
    token = eval_resp.get("approval_token")

    if token is None:
        evidence.flush("PASS (no token issued — prerequisite for exploit not met)")
        pytest.skip("Policy Gate did not issue a token for the fabricated price (see the other test in this file)")

    order_resp = post(f"{BACKEND_URL}/order/create", {"product_id": 1, "quantity": 1, "approval_token": token})
    order_body = order_resp.json() if order_resp.headers.get("content-type", "").startswith("application/json") else {"raw": order_resp.text}
    evidence.record(
        "redeem_via_real_order_create",
        request={"product_id": 1, "quantity": 1, "approval_token": token},
        status_code=order_resp.status_code,
        response=order_body,
    )

    exploited = order_resp.status_code == 200 and order_body.get("amount") == fake_discounted_value
    verdict = "FAIL (vulnerable — full exploit succeeded)" if exploited else "PASS (checkout blocked the fraudulent token)"
    evidence.flush(
        verdict,
        notes=(
            f"A real Razorpay order (id={order_body.get('razorpay_order_id')}) was created for "
            f"Rs {order_body.get('amount', 0)/100:.2f} on a product actually listed at Rs {real_price/100:.2f}."
            if exploited
            else ""
        ),
    )

    assert not exploited, (
        f"SECURITY BUG: checkout created a real order for {order_body.get('amount')} paise "
        f"(razorpay_order_id={order_body.get('razorpay_order_id')}) on product 1, which actually costs "
        f"{real_price} paise. Full exploit chain: fabricate original_price at Policy Gate -> get a valid "
        "token -> redeem it through the normal /order/create checkout path, with zero code changes and zero "
        "authentication bypass — just calling Policy Gate's own public API directly."
    )
