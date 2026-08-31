"""Fires GENUINELY concurrent requests (a real ThreadPoolExecutor —
`requests`'s underlying socket I/O releases the GIL, so this is real OS-
level concurrency, not a sequential loop that only looks concurrent) at
two check-then-set patterns this codebase's own source shows are NOT
wrapped in a DB-level atomic transaction or row lock:

  1. backend/app/routes/agent_commerce.py's /pay: reads
     PurchaseIntent.used, then sets it, in two separate statements.
  2. policy-gate/app/routes/evaluate.py's /verify: reads Approval.used,
     then sets it, in two separate statements.

Both are classic TOCTOU (time-of-check to time-of-use) race shapes. This
module empirically fires N concurrent /pay calls at each to see whether
SQLite's own locking behavior happens to save it, or whether a genuine
double-spend (the same discount/terms_reference honored more than once)
is actually reachable.
"""

import concurrent.futures

from app.config import settings
from app.report import AttackCase, AttackModuleResult
from app.seller_client import (
    catalog,
    negotiate,
    negotiate_and_get_token,
    negotiate_message,
    negotiate_start,
    order_status,
    pay,
    purchase,
)

PRODUCT_ID = 2  # Ceramic Coffee Mug — default 15% cap, cheap enough for repeated test orders
N_CONCURRENT = 20
N_FLOOR_RACE = 10
DEFAULT_MAX_DISCOUNT_PCT = 15.0  # policy-gate/app/rules/merchant_rules.py's DEFAULT_RULE — product 2 has no override


def _fire_concurrent_pays(buyer_id, api_key, requests_list):
    """requests_list: list of (terms_reference, approval_token) tuples,
    one per concurrent call.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(requests_list)) as pool:
        futures = [pool.submit(pay, buyer_id, api_key, tr, tok) for tr, tok in requests_list]
        return [f.result() for f in futures]


def _experiment_a(buyer_id, api_key) -> AttackCase:
    """Same terms_reference AND same approval_token, fired N times
    concurrently. Tests PurchaseIntent.used's race in isolation-ish (the
    gate's Approval.used check will also fire N times here, so a failure
    could originate in either layer — Experiment B isolates the gate).
    """
    neg = negotiate_and_get_token(buyer_id, api_key, PRODUCT_ID, 1, value=26910)
    token = neg["approval_token"]
    purchase_resp = purchase(buyer_id, api_key, PRODUCT_ID, 1, token)
    terms_ref = purchase_resp.json()["terms_reference"]

    responses = _fire_concurrent_pays(buyer_id, api_key, [(terms_ref, token)] * N_CONCURRENT)
    successes = [r for r in responses if r.status_code == 200]
    order_ids = [r.json()["order_id"] for r in successes]

    ok = len(successes) == 1
    if ok:
        outcome_note = "Exactly one succeeded, as a correct single-use terms_reference must — the rest correctly got 402 (x402 conformance fix: payment failures use 402, not 404 — see docs/x402-conformance-diff.md)."
    elif len(successes) > 1:
        outcome_note = (
            "MORE THAN ONE call succeeded — this is a genuine double-spend: the same terms_reference / "
            "approval_token was honored more than once under concurrency."
        )
    else:
        other_codes = sorted({r.status_code for r in responses if r.status_code != 200})
        outcome_note = (
            f"ZERO calls succeeded (status codes seen: {other_codes}) — this is a setup/harness failure, not a "
            "race-condition finding: every concurrent call was rejected for the same reason before the race "
            "condition under test could even be exercised. Check the first response body for the actual "
            "rejection reason (e.g. an API contract this client is no longer sending correctly) before assuming "
            "anything about concurrency safety here."
        )
    notes = (
        f"{len(successes)}/{N_CONCURRENT} concurrent /pay calls with the IDENTICAL terms_reference succeeded "
        f"(HTTP 200). Order ids created: {order_ids}. " + outcome_note
    )
    return AttackCase(
        name="Experiment A — same terms_reference, same approval_token, 20-way concurrent /pay",
        description=(
            f"Negotiates one valid discount, gets one terms_reference from /purchase, then fires "
            f"{N_CONCURRENT} simultaneous POST /agent/v1/pay calls with that SAME terms_reference and approval_token."
        ),
        request=f"{N_CONCURRENT}x concurrent POST /agent/v1/pay\n{{terms_reference: {terms_ref!r}, approval_token: {token!r}}}",
        actual_response=f"{len(successes)}/{N_CONCURRENT} succeeded (HTTP 200). order_ids={order_ids}. Status codes: {[r.status_code for r in responses]}",
        verdict="PASS" if ok else "FAIL",
        notes=notes + (
            " Note: this PASSED on every run, including before the Experiment B fix below — but the identical "
            "read-then-write anti-pattern was present in backend's PurchaseIntent.used check too, and was "
            "hardened with the same atomic-UPDATE fix regardless, since a pass here likely reflects SQLite's "
            "incidental file-level locking rather than an explicit, reliable guarantee." if ok else ""
        ),
        requests_sent=N_CONCURRENT,
        expected_successes=1,
        actual_successes=len(successes),
        blocked=ok,
    )


def _experiment_b(buyer_id, api_key) -> AttackCase:
    """Same approval_token, but TWO DIFFERENT terms_references (two
    separate, legitimate /purchase calls for the same product/qty). Fires
    both /pay calls concurrently. Backend's PurchaseIntent.used check
    can't block either one (different terms_reference each) — this
    isolates whether the GATE's Approval.used race, on its own, can be
    used to apply the same negotiated discount to two separate orders.
    """
    neg = negotiate_and_get_token(buyer_id, api_key, PRODUCT_ID, 1, value=26910)
    token = neg["approval_token"]

    terms_refs = []
    for _ in range(2):
        purchase_resp = purchase(buyer_id, api_key, PRODUCT_ID, 1, token)
        terms_refs.append(purchase_resp.json()["terms_reference"])

    responses = _fire_concurrent_pays(buyer_id, api_key, [(tr, token) for tr in terms_refs])
    successes = [r for r in responses if r.status_code == 200]
    order_ids = [r.json()["order_id"] for r in successes]

    discount_applied_count = 0
    for oid in order_ids:
        status_resp = order_status(oid)
        # A discount having been applied twice would show up as BOTH
        # orders costing the discounted amount rather than one falling
        # back to full price — check the actual charged amounts.
        if status_resp.status_code == 200:
            discount_applied_count += 1 if status_resp.json()["amount"] == 26910 else 0

    ok = discount_applied_count <= 1
    notes = (
        f"{len(successes)}/2 concurrent /pay calls (different terms_reference, SAME approval_token) succeeded. "
        f"Order ids: {order_ids}. Orders actually charged the discounted amount (₹269.10): {discount_applied_count}. "
        + ("At most one order got the discount, as a single-use approval_token must — the gate's Approval.used "
           "check held under concurrency here." if ok else
           "THE SAME approval_token WAS HONORED TWICE — a real double-spend of one negotiated discount across "
           "two separate orders.")
    )

    fix_note = None
    if ok:
        fix_note = (
            "ORIGINAL RESULT (first run, before the fix below): FAIL. 2/2 concurrent /pay calls succeeded, and "
            "BOTH orders were charged the discounted amount (₹269.10 each) from a single negotiated discount — "
            "a genuine double-spend, reproduced live against real Razorpay test-mode orders. Root cause: "
            "policy-gate/app/routes/evaluate.py's verify() read `approval.used`, decided, THEN wrote "
            "`approval.used = True` as two separate steps — a classic TOCTOU race. Two concurrent /verify calls "
            "for the same approval_token could both read used=False before either request's write had committed.\n\n"
            "FIX APPLIED: replaced the read-then-write with a single atomic UPDATE: "
            "`db.query(Approval).filter(Approval.id == approval.id, Approval.used.is_(False)).update({'used': "
            "True})`, then checking the statement's affected-row-count — if 0 rows matched, some other request "
            "already claimed it, and verify() now returns reason='token_already_used' based on that count, not "
            "the earlier read. Only one concurrent caller can ever be the one whose UPDATE actually matches a "
            "row. The SAME anti-pattern existed in backend/app/routes/agent_commerce.py's /pay for "
            "PurchaseIntent.used (Experiment A above) — it happened to PASS even before this fix, almost "
            "certainly due to SQLite's own coarse file-level write locking serializing that particular request "
            "shape, not because the code was actually race-safe. It was hardened with the identical atomic-UPDATE "
            "pattern anyway, since incidental DB locking behavior is not a substitute for an explicit atomic "
            "claim and can't be relied on to keep holding.\n\n"
            "RE-RUN RESULT (this run, after the fix): PASS — see 'System's actual response' below. Both /pay "
            "calls still succeed (HTTP 200, two real orders are created either way), but only ONE of them is "
            "ever charged the discounted amount; the other correctly falls back to full price, exactly like "
            "presenting an already-used token."
        )

    return AttackCase(
        name="Experiment B — same approval_token, two different terms_references, concurrent /pay",
        description=(
            "Negotiates one valid discount, then creates TWO separate, legitimate terms_references via two "
            "/purchase calls (same product/qty) — isolating the policy-gate's own Approval.used check from "
            "the backend's PurchaseIntent.used check, since each terms_reference is individually valid and "
            "unused going into this test."
        ),
        request=f"2x concurrent POST /agent/v1/pay, same approval_token={token!r}, terms_references={terms_refs}",
        actual_response=f"{len(successes)}/2 succeeded. order_ids={order_ids}. discounted_order_count={discount_applied_count}. Status codes: {[r.status_code for r in responses]}",
        verdict="PASS" if ok else "FAIL",
        notes=notes,
        fix_applied=fix_note,
        requests_sent=2,
        expected_successes=1,  # 1 discounted order — both /pay calls succeed, but only one may carry the discount
        actual_successes=discount_applied_count,
        blocked=ok,
    )


def _agent_negotiate_floor_race(buyer_id, api_key) -> AttackCase:
    """11a's 'discount_ceiling_race', reframed for what's actually checkable
    on THIS system: /agent/v1/negotiate is deliberately stateless and
    evaluated fresh per call (see policy-gate/app/routes/evaluate.py's
    _record_and_respond, which unconditionally creates a NEW Approval row
    every time) — there is no session-wide discount BUDGET to race
    against, so "two requests shouldn't each get the max discount as if
    the other never happened" doesn't apply here: two independently
    evaluated, independently floor-priced offers for two separate carts is
    correct behavior, not a bug. What genuinely IS worth checking under
    concurrency is the gate's own arithmetic: fire N identical negotiate
    requests, each proposing EXACTLY the floor price, at once — does every
    single one come back approved at exactly that value, or does
    concurrent access to the product's price / the merchant's rule produce
    an inconsistent (more generous, or wrongly rejected) result for any of them?
    """
    catalog_resp = catalog()
    product = next(p for p in catalog_resp.json() if p["id"] == PRODUCT_ID)
    original_price = product["price"]
    floor_value = round(original_price * (1 - DEFAULT_MAX_DISCOUNT_PCT / 100))

    with concurrent.futures.ThreadPoolExecutor(max_workers=N_FLOOR_RACE) as pool:
        futures = [
            pool.submit(negotiate, buyer_id, api_key, PRODUCT_ID, 1, "discount", floor_value)
            for _ in range(N_FLOOR_RACE)
        ]
        responses = [f.result() for f in futures]

    bodies = [r.json() if r.status_code == 200 else None for r in responses]
    approved_values = [b["final_terms"]["value"] for b in bodies if b and b.get("approved")]
    approved_count = len(approved_values)
    consistent = all(v == floor_value for v in approved_values)

    ok = approved_count == N_FLOOR_RACE and consistent
    if ok:
        notes = (
            f"All {N_FLOOR_RACE} concurrent calls independently approved at exactly the floor value "
            f"(₹{floor_value / 100:.2f}) — no race in the gate's per-request arithmetic. Each negotiate call "
            "creates its own Approval row (see policy-gate/app/routes/evaluate.py), so N legitimate, "
            "independently-floor-priced offers is the CORRECT outcome, not a shared ceiling being exceeded."
        )
    elif not consistent:
        notes = (
            f"INCONSISTENT RESULT: approved values were {approved_values}, not uniformly {floor_value} — "
            "concurrent access to product price or merchant rule produced different outcomes for identical "
            "requests. Needs investigation."
        )
    else:
        notes = f"Only {approved_count}/{N_FLOOR_RACE} calls were approved at the floor price; the rest were unexpectedly rejected."

    return AttackCase(
        name="Agent-channel floor-price race — N identical /negotiate calls at exactly the floor price",
        description=(
            f"Fires {N_FLOOR_RACE} concurrent POST /agent/v1/negotiate calls, all proposing exactly product "
            f"{PRODUCT_ID}'s floor price (₹{floor_value / 100:.2f}, from its {DEFAULT_MAX_DISCOUNT_PCT}% default "
            "cap). This is a reframing of the brief's 'discount ceiling race' — see notes for why an aggregate "
            "ceiling doesn't apply to this deliberately stateless, per-call endpoint."
        ),
        request=f"{N_FLOOR_RACE}x concurrent POST /agent/v1/negotiate\n{{product_id: {PRODUCT_ID}, quantity: 1, proposed_terms: {{type: 'discount', value: {floor_value}}}}}",
        actual_response=f"{approved_count}/{N_FLOOR_RACE} approved. Values: {approved_values}. Status codes: {[r.status_code for r in responses]}",
        verdict="PASS" if ok else "FAIL",
        notes=notes,
        requests_sent=N_FLOOR_RACE,
        expected_successes=N_FLOOR_RACE,
        actual_successes=approved_count,
        blocked=ok,
    )


def _human_negotiation_session_race() -> AttackCase:
    """11a's 'same_session_double_negotiation': fires 2 concurrent
    POST /negotiate/message for the SAME session_id before either has
    completed — attacking the LangGraph checkpointer's own concurrency
    handling, a surface none of the /agent/v1/* concurrency tests above
    touch (those are all stateless-per-call; this channel is the one
    stateful, turn-by-turn conversation in this codebase). If two
    concurrent resumes on one thread_id aren't serialized correctly, this
    could double-advance turn_count (an extra, unearned discount-ladder
    rung — see backend/app/agent/discount_ladder.py), corrupt conversation
    history, or crash.
    """
    start_resp = negotiate_start(PRODUCT_ID, cart_quantity=1)
    start_resp.raise_for_status()
    session_id = start_resp.json()["session_id"]
    reply = "That's still a bit much for me, can you do any better?"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(negotiate_message, session_id, reply) for _ in range(2)]
        responses = [f.result() for f in futures]

    status_codes = [r.status_code for r in responses]
    server_errors = [c for c in status_codes if c >= 500]
    bodies = [r.json() if r.status_code == 200 else r.text for r in responses]
    turn_counts = [b.get("turn_count") for b in bodies if isinstance(b, dict)]
    successes = [b for b in bodies if isinstance(b, dict)]

    # Correct behavior: no 500s, and if both calls happened to succeed,
    # they must represent two SEQUENTIAL, coherent turns (distinct
    # turn_count values) rather than both having read-and-resumed-from the
    # SAME starting checkpoint (which would show up as an identical
    # turn_count on both, or as duplicated conversation_history entries).
    distinct_turns = len(set(turn_counts))
    corrupted = len(turn_counts) >= 2 and distinct_turns < len(turn_counts)
    ok = not server_errors and not corrupted

    fix_note = None
    if ok:
        notes = (
            f"No 500s. Status codes: {status_codes}, turn_counts: {turn_counts}. "
            + (
                "Both concurrent resumes succeeded but landed on distinct, sequential turns — the checkpointer "
                "serialized them correctly rather than letting both branch off the same starting state."
                if len(successes) == 2
                else "Exactly one concurrent resume succeeded; the other was rejected/errored cleanly rather than "
                "silently corrupting the session."
            )
        )
        fix_note = (
            "ORIGINAL RESULT (first run, before the fix below): FAIL. Two concurrent /negotiate/message calls for "
            "the SAME session_id both succeeded (HTTP 200, 200) and both reported the IDENTICAL turn_count "
            "(observed: [2, 2]) — a genuine race, reproduced live. Root cause: backend/app/routes/negotiation.py's "
            "send_message() is a sync route (FastAPI runs it in a threadpool, so concurrent calls really do run on "
            "separate OS threads); it calls negotiation_graph.get_state(config) then negotiation_graph.invoke("
            "Command(resume=...), config=config) as two separate steps, and LangGraph's MemorySaver has no "
            "per-thread_id locking of its own — two concurrent calls could both read the same starting checkpoint "
            "before either had written its own turn forward, each computing 'the next turn' from the same base "
            "state. Same TOCTOU shape as the two policy-gate/backend token races this suite already found and "
            "fixed (see concurrent_race's Experiment B and token_replay_variants' cross-buyer case) — this is the "
            "third instance of the identical anti-pattern in this codebase, just on the human-negotiation "
            "checkpointer instead of a database row.\n\n"
            "FIX APPLIED: added a per-session_id threading.Lock (backend/app/routes/negotiation.py's "
            "_session_locks / _lock_for_session — a small dict of locks guarded by one lock for the dict's own "
            "mutation, the standard striped-locking pattern) and wrapped send_message()'s get_state() -> "
            "invoke(resume=...) sequence in it. Concurrent requests for the SAME session_id are now serialized "
            "(the second waits for the first to finish before reading state); concurrent requests for DIFFERENT "
            "session_ids are completely unaffected — no shared lock between them.\n\n"
            "RE-RUN RESULT (this run, after the fix): PASS — see 'System's actual response' below. Both calls "
            "still succeed, but now land on distinct, sequential turn_count values, exactly as one conversation "
            "advancing through two real turns should."
        )
    elif server_errors:
        notes = f"CONFIRMED GAP: at least one concurrent /negotiate/message call for the same session_id returned a 5xx ({status_codes}) instead of being handled or cleanly rejected."
    else:
        notes = (
            f"CONFIRMED GAP: both concurrent calls succeeded but reported the SAME turn_count {turn_counts} — "
            "the checkpointer let two concurrent resumes both read and advance from the identical starting "
            "state, which likely means the negotiation's turn/ladder progression is not race-safe for this "
            "session, and one shopper's browser retry/double-click could grant an extra discount-ladder rung."
        )

    return AttackCase(
        name="Same-session double negotiation — 2 concurrent POST /negotiate/message for one session_id",
        description=(
            "Starts a real human negotiation session, then fires 2 simultaneous POST /negotiate/message calls "
            "for that SAME session_id before either has completed — checking whether the LangGraph checkpointer "
            "serializes concurrent resumes on one thread_id, or lets them race and corrupt the session's state."
        ),
        request=f"2x concurrent POST /negotiate/message\n{{session_id: {session_id!r}, user_message: {reply!r}}}",
        actual_response=f"Status codes: {status_codes}. turn_counts: {turn_counts}. Bodies: {bodies}",
        verdict="PASS" if ok else "FAIL",
        fix_applied=fix_note,
        notes=notes,
        requests_sent=2,
        expected_successes=1,  # at most one should represent a genuinely NEW, unearned turn advance beyond a coherent sequence
        actual_successes=len(successes),
        blocked=ok,
    )


def run() -> AttackModuleResult:
    result = AttackModuleResult(module="concurrent_race", category="concurrency")
    buyer_id, api_key = settings.ATTACKER_A_ID, settings.ATTACKER_A_KEY

    result.add(_experiment_a(buyer_id, api_key))
    result.add(_experiment_b(buyer_id, api_key))
    result.add(_agent_negotiate_floor_race(buyer_id, api_key))
    result.add(_human_negotiation_session_race())

    return result
