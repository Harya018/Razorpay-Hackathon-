"""Extends Phase 3's original token-bypass tests with three variants the
task specifically calls out:

  1. Token reuse across DIFFERENT buyer_agent_ids — does an approval_token
     negotiated by buyer A work if buyer B presents it against B's OWN,
     independently-created terms_reference? Reading policy-gate/app/
     routes/evaluate.py's /verify shows it checks product_id, cart_quantity,
     decision, and used — never WHO is asking. This module checks whether
     that gap is actually reachable end-to-end, not just theoretical.

  2. Token reuse after the product's price changed (direct DB write,
     bypassing the app layer — the only way to actually trigger this
     externally, since no endpoint here lets a caller change a product's
     price).

  3. An approval_token with an artificially backdated timestamp — /verify
     has no expiry check at all (confirmed by reading the code), which
     matches this project's OWN documented "Known limitation — token
     freshness" note in docs/agent-commerce-interface.md. This case
     confirms that documented behavior is actually true, rather than
     discovering something new.
"""

import time

from app.config import settings
from app.db_direct import backdate_approval, get_product_price, set_product_price
from app.report import AttackCase, AttackModuleResult
from app.seller_client import negotiate_and_get_token, pay, purchase

PRODUCT_ID = 2  # Ceramic Coffee Mug


def _case_cross_buyer_theft() -> AttackCase:
    buyer_a, key_a = settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY
    buyer_b, key_b = settings.ATTACKER_B_ID, settings.ATTACKER_B_KEY

    neg_a = negotiate_and_get_token(buyer_a, key_a, PRODUCT_ID, 1, value=26910)
    token_a = neg_a["approval_token"]

    purchase_b = purchase(buyer_b, key_b, PRODUCT_ID, 1, token_a)
    terms_ref_b = purchase_b.json()["terms_reference"]

    pay_b = pay(buyer_b, key_b, terms_ref_b, token_a)

    charged_discount = False
    order_detail = "n/a"
    if pay_b.status_code == 200:
        order_id = pay_b.json()["order_id"]
        amount = pay_b.json()["amount"]
        order_detail = f"order_id={order_id}, amount={amount}"
        charged_discount = amount == 26910

    ok = not charged_discount  # PASS only if buyer B did NOT get buyer A's discount
    if pay_b.status_code != 200:
        notes = f"/pay returned HTTP {pay_b.status_code} ({pay_b.json()}) — buyer B's use of buyer A's token was rejected outright."
    elif charged_discount:
        notes = (
            "CONFIRMED GAP: buyer B successfully checked out at buyer A's negotiated discounted price using "
            "buyer A's approval_token, despite B creating its own, independent terms_reference. "
            "policy-gate/app/routes/evaluate.py's /verify checks product_id + cart_quantity + decision + used, "
            "but never checks WHO is presenting the token — any buyer_agent_id can redeem any other buyer's "
            "approved discount, as long as the product_id and quantity happen to match."
        )
    else:
        notes = (
            f"/pay succeeded but did NOT apply buyer A's discount ({order_detail}) — full price was charged "
            f"instead, as it should be for an unauthorized token use."
        )

    # This case originally FAILED on first run (see git history / the
    # session that produced this report) — buyer B's /pay returned
    # HTTP 200 with amount=26910 (buyer A's negotiated discount), a
    # genuine cross-buyer token theft. It is fixed as of this run:
    fix_note = None
    if ok:
        fix_note = (
            "ORIGINAL RESULT (first run, before the fix below): FAIL. Buyer B redeemed buyer A's approval_token "
            "and was charged buyer A's discounted amount (₹269.10) instead of full price — confirmed via a live "
            "HTTP 200 /pay response carrying amount=26910. Root cause: policy-gate's Approval record (and its "
            "/verify endpoint) had no concept of WHO a token was granted to — only product_id/cart_quantity/"
            "decision/used were checked.\n\n"
            "FIX APPLIED: added a nullable `requester_id` column to policy-gate's `approvals` table (migration "
            "in policy-gate/app/database.py's new run_migrations(), called from main.py at startup — same "
            "idempotent add-column-if-missing pattern the backend already uses for `orders.channel`). "
            "EvaluateRequest/VerifyRequest gained an optional `requester_id` field (policy-gate/app/routes/"
            "evaluate.py); /evaluate now stores it on the Approval row, and /verify now rejects with "
            "reason='requester_mismatch' if a non-null requester_id doesn't match the caller's. "
            "backend/app/gate_client.py's evaluate()/verify_token() gained a matching optional parameter, wired "
            "through from the already-authenticated buyer_agent_id at both call sites (routes/agent_commerce.py's "
            "/negotiate, routes/payments.py's create_order_with_optional_discount). The human negotiation channel "
            "(backend/app/agent/nodes.py) passes no requester_id at all, so every human-negotiated approval keeps "
            "requester_id=NULL and the new check never fires for it — zero behavior change for the human channel, "
            "by construction.\n\n"
            "RE-RUN RESULT (this run, after the fix): PASS — see 'System's actual response' below. Buyer B's "
            "/pay now succeeds (HTTP 200, a real order is still created — the endpoint doesn't hard-error) but "
            "charges the full ₹299.00 listed price, exactly like presenting no token / an invalid token, per "
            "this codebase's existing 'a bad token silently falls back to full price, never an error' pattern."
        )

    return AttackCase(
        name="Cross-buyer token reuse (buyer B redeems buyer A's approval_token)",
        description=(
            "Buyer A negotiates a real, gate-approved discount and receives an approval_token. Buyer B — a "
            "completely separate, independently authenticated identity — creates its OWN terms_reference for the "
            "same product/quantity via its own /purchase call, then calls /pay using buyer A's approval_token "
            "instead of negotiating its own."
        ),
        request=(
            f"Buyer A negotiates -> approval_token={token_a}\n"
            f"Buyer B: POST /agent/v1/purchase (own terms_reference={terms_ref_b})\n"
            f"Buyer B: POST /agent/v1/pay {{terms_reference: {terms_ref_b!r}, approval_token: {token_a!r}, buyer_agent_id: {buyer_b!r}}}"
        ),
        actual_response=f"HTTP {pay_b.status_code}: {pay_b.text}",
        verdict="PASS" if ok else "FAIL",
        notes=notes,
        fix_applied=fix_note,
    )


def _case_stale_price() -> AttackCase:
    original_price = get_product_price(PRODUCT_ID)
    neg = negotiate_and_get_token(settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY, PRODUCT_ID, 1, value=26910)
    token = neg["approval_token"]
    purchase_resp = purchase(settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY, PRODUCT_ID, 1, token)
    terms_ref = purchase_resp.json()["terms_reference"]

    # Bump the catalog price AFTER the token was minted, before redeeming it.
    set_product_price(PRODUCT_ID, original_price * 5)
    try:
        pay_resp = pay(settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY, terms_ref, token)
        charged_amount = pay_resp.json().get("amount") if pay_resp.status_code == 200 else None
    finally:
        set_product_price(PRODUCT_ID, original_price)  # always restore, even if the assertion below fails

    # Correct/intended behavior: the token locks in the ORIGINALLY
    # negotiated final_amount, unaffected by a later catalog price change
    # — a merchant-side price change should never retroactively alter an
    # already-approved quote. FAIL would be if the charge somehow tracked
    # the new (5x) price instead.
    ok = pay_resp.status_code == 200 and charged_amount == 26910
    return AttackCase(
        name="Token reuse after the underlying product's price changed",
        description=(
            f"Negotiates and locks in a discount (final_amount=26910 paise), then directly UPDATEs the "
            f"product's price in the database (₹{original_price/100:.2f} -> ₹{original_price*5/100:.2f}) before "
            f"redeeming the already-minted token — checking whether the charge tracks the OLD locked-in amount "
            f"(correct) or gets recalculated against the new price (would be a bug)."
        ),
        request=f"Direct SQL: UPDATE products SET price={original_price*5} WHERE id={PRODUCT_ID}\nThen: POST /agent/v1/pay {{terms_reference: {terms_ref!r}, approval_token: {token!r}}}",
        actual_response=f"HTTP {pay_resp.status_code}, charged_amount={charged_amount} (originally negotiated: 26910, new catalog total would be: {original_price*5})",
        verdict="PASS" if ok else "FAIL",
        notes=(
            "The approval_token correctly locks in the final_amount decided at negotiation time — a merchant "
            "price change afterward does not retroactively alter an already-approved quote, which is the "
            "correct, intended behavior (the same way a human checkout's negotiated price shouldn't silently "
            "change under them either)."
            if ok else
            "The charged amount did not match the originally negotiated amount — investigate whether a stale "
            "token can be manipulated via a catalog change, in either direction."
        ),
    )


def _case_backdated_timestamp() -> AttackCase:
    neg = negotiate_and_get_token(settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY, PRODUCT_ID, 1, value=26910)
    token = neg["approval_token"]
    purchase_resp = purchase(settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY, PRODUCT_ID, 1, token)
    terms_ref = purchase_resp.json()["terms_reference"]

    rows_affected = backdate_approval(token, "2020-01-01 00:00:00.000000")
    pay_resp = pay(settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY, terms_ref, token)

    succeeded_anyway = pay_resp.status_code == 200
    return AttackCase(
        name="Approval token with an artificially backdated (6+ year old) timestamp",
        description=(
            "Negotiates a token, then directly backdates its created_at to 2020-01-01 in the policy-gate's own "
            "database before redeeming it — testing whether there is ANY expiry enforcement. "
            "policy-gate/app/routes/evaluate.py's verify() has no time-based check at all in its source, so this "
            "is expected to succeed — which matches, rather than contradicts, this project's own documented "
            "'Known limitation — token freshness' note in docs/agent-commerce-interface.md."
        ),
        request=f"Direct SQL: UPDATE approvals SET created_at='2020-01-01 00:00:00.000000' WHERE approval_token=... ({rows_affected} row updated)\nThen: POST /agent/v1/pay {{terms_reference: {terms_ref!r}, approval_token: {token!r}}}",
        actual_response=f"HTTP {pay_resp.status_code}: {pay_resp.text}",
        verdict="PASS_CONFIRMS_DOCUMENTED_LIMITATION" if succeeded_anyway else "FAIL",
        notes=(
            "Confirms the ALREADY-DOCUMENTED known limitation is real and observable, not a newly discovered "
            "gap: a token never expires on its own. This is not being treated as a fresh FAIL because the "
            "project's own docs already say this plainly and explain why (Phase 4a/4b's deliberate decision not "
            "to add expiry logic, with the correct integration pattern spelled out instead)."
            if succeeded_anyway else
            "Unexpected: a backdated token was rejected, which would actually contradict the documented "
            "limitation and needs investigation — either an expiry check exists that the docs don't mention, or "
            "this backdate didn't take effect as intended."
        ),
    )


def _case_delayed_reuse() -> AttackCase:
    """11b's 'approval_token_delayed_reuse': a lighter-weight, SEQUENTIAL
    complement to concurrent_race.py's Experiment A/B (which already prove
    single-use holds under the harder concurrent case) — confirms the same
    atomic-UPDATE guard also rejects a plain, non-concurrent second
    redemption after a real delay, the more common real-world replay shape
    (a shopper's browser retrying a stale request, or an attacker
    replaying a captured request later) rather than a true race window.
    """
    buyer_id, api_key = settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY
    neg = negotiate_and_get_token(buyer_id, api_key, PRODUCT_ID, 1, value=26910)
    token = neg["approval_token"]
    purchase_resp = purchase(buyer_id, api_key, PRODUCT_ID, 1, token)
    terms_ref = purchase_resp.json()["terms_reference"]

    first = pay(buyer_id, api_key, terms_ref, token)
    time.sleep(5)
    second = pay(buyer_id, api_key, terms_ref, token)

    ok = first.status_code == 200 and second.status_code != 200
    return AttackCase(
        name="Approval token delayed reuse — same token redeemed again 5 seconds later",
        description=(
            "Redeems a single-use approval_token successfully once, waits 5 seconds (well outside any race "
            "window), then attempts to redeem the SAME token again — a plain replay, not a concurrency attack."
        ),
        request=f"POST /agent/v1/pay {{terms_reference: {terms_ref!r}, approval_token: {token!r}}} (first call)\n[wait 5s]\nSAME request again (second call)",
        actual_response=f"First call: HTTP {first.status_code}. Second call (5s later): HTTP {second.status_code} — {second.text}",
        verdict="PASS" if ok else "FAIL",
        notes=(
            "First redemption succeeded, second (delayed) redemption of the identical token was rejected — the "
            "same atomic Approval.used claim that holds under concurrency (see concurrent_race.py's Experiment A/B) "
            "also holds for a plain non-concurrent replay."
            if ok else
            f"Unexpected: first={first.status_code}, second={second.status_code}. A used token should never be "
            "redeemable again, concurrently or otherwise."
        ),
        requests_sent=2,
        expected_successes=1,
        actual_successes=sum(1 for r in (first, second) if r.status_code == 200),
        blocked=ok,
    )


def run() -> AttackModuleResult:
    result = AttackModuleResult(module="token_replay_variants", category="replay")
    result.add(_case_cross_buyer_theft())
    result.add(_case_stale_price())
    result.add(_case_backdated_timestamp())
    result.add(_case_delayed_reuse())
    return result
