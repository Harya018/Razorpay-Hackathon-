"""17.4 — Buyer agent human-checkpoint timeout.

Goal (as specified): prove silence never defaults to "proceed."

REALITY CHECK (traced in buyer-agent/app/graph/nodes.py +
buyer-agent/app/graph/graph.py before writing this test): there is NO
timeout/expiry mechanism in this codebase at all. `await_negotiate_checkpoint`
and `await_purchase_confirmation` both call LangGraph's `interrupt()`,
which halts graph execution outright — `buyer_graph.invoke()` only ever
resumes via an explicit `Command(resume=...)` triggered by a real
POST /shopper/chat call. There is no timer, no background task, no
"if N seconds pass, treat as declined" branch anywhere. `MemorySaver`
(the checkpointer) just holds the paused state in memory forever.

That actually makes the core safety property STRONGER than a
timeout-triggered abort, not weaker: it is not that silence gets
detected and turned into a rejection — it's that the graph is
structurally incapable of advancing on its own. There is no code path
between "human says nothing" and "purchase proceeds." This test proves
that property behaviorally (waiting a real, nontrivial period with no
reply, confirming nothing advanced, then resuming normally afterward).

The genuinely missing piece — flagged in WHAT_BROKE.md, not smoothed
over — is that this also means an abandoned session NEVER expires or
gets cleaned up, and there is no "timeout" event logged anywhere,
because the concept doesn't exist in this code. The task's literal ask
("assert the agent aborts... and logs the abort reason") does not apply
as written; what's tested instead is the property that actually matters
for the trust boundary (no silent auto-proceed), stated honestly.
"""

import time

import pytest

from conftest import BACKEND_URL, BUYER_AGENT_URL, get, post

SILENCE_WAIT_SECONDS = 12  # a real wait, not a configured timeout (none exists) — see module docstring


@pytest.mark.usefixtures("require_buyer_agent")
def test_negotiate_checkpoint_does_not_auto_proceed_during_silence(evidence):
    orders_before = get(f"{BACKEND_URL}/dashboard/summary").json()["total_orders"]

    start_resp = post(
        f"{BUYER_AGENT_URL}/shopper/start",
        {
            "goal": (
                "I'm interested in the hand-painted ceramic vase. Please try to negotiate a discount on it — "
                "my ideal price is 2000 rupees, but go ahead and negotiate even if you can't fully reach that, "
                "I still want to see the best offer."
            )
        },
    ).json()
    evidence.record("shopper_start", response=start_resp)

    if start_resp.get("awaiting") != "negotiate_checkpoint":
        pytest.skip(f"This run didn't land on negotiate_checkpoint (got {start_resp.get('awaiting')!r}) — LLM framing is non-deterministic run to run")

    session_id = start_resp["session_id"]

    evidence.record("begin_silence", wait_seconds=SILENCE_WAIT_SECONDS)
    time.sleep(SILENCE_WAIT_SECONDS)

    orders_during_silence = get(f"{BACKEND_URL}/dashboard/summary").json()["total_orders"]
    evidence.record("orders_check_after_silence", orders_before=orders_before, orders_now=orders_during_silence)

    # Now actually respond — proves the checkpoint is still exactly where
    # we left it (not expired, not auto-advanced to some other state).
    resume_resp = post(f"{BUYER_AGENT_URL}/shopper/chat", {"session_id": session_id, "message": "cancel"}).json()
    evidence.record("resume_after_silence", response=resume_resp)

    verdict = "PASS"
    problems = []
    if orders_during_silence != orders_before:
        verdict = "FAIL"
        problems.append(f"order count changed during silence ({orders_before} -> {orders_during_silence}) with no human reply")
    if not resume_resp.get("done") or "declin" not in resume_resp.get("message", "").lower():
        verdict = "FAIL"
        problems.append(f"expected a clean cancellation after the silence window; got: {resume_resp}")

    evidence.flush(
        verdict,
        notes="No timeout mechanism exists in this codebase (see module docstring) — this test proves the "
        "stronger property that matters: silence cannot advance the graph at all, verified by waiting "
        f"{SILENCE_WAIT_SECONDS}s with no reply, confirming no order was created, then resuming normally. "
        + "; ".join(problems),
    )

    assert orders_during_silence == orders_before, (
        f"SECURITY BUG: an order was created while a human-in-the-loop checkpoint was awaiting a reply with "
        f"total silence ({orders_before} -> {orders_during_silence})."
    )
    assert resume_resp.get("done") is True and "declin" in resume_resp.get("message", "").lower(), (
        f"Expected the checkpoint to still be live and cancellable after the silence window; got: {resume_resp}"
    )


@pytest.mark.usefixtures("require_buyer_agent")
def test_purchase_confirmation_checkpoint_does_not_auto_proceed_during_silence(evidence):
    orders_before = get(f"{BACKEND_URL}/dashboard/summary").json()["total_orders"]

    start_resp = post(
        f"{BUYER_AGENT_URL}/shopper/start",
        {"goal": "I want a hand-thrown stoneware mug, no need to negotiate, just buy one"},
    ).json()
    evidence.record("shopper_start", response=start_resp)

    if start_resp.get("done") or start_resp.get("awaiting") != "purchase_confirmation":
        pytest.skip(f"This run didn't land on purchase_confirmation directly (got {start_resp}) — LLM framing is non-deterministic")

    session_id = start_resp["session_id"]

    evidence.record("begin_silence", wait_seconds=SILENCE_WAIT_SECONDS)
    time.sleep(SILENCE_WAIT_SECONDS)

    orders_during_silence = get(f"{BACKEND_URL}/dashboard/summary").json()["total_orders"]
    evidence.record("orders_check_after_silence", orders_before=orders_before, orders_now=orders_during_silence)

    resume_resp = post(f"{BUYER_AGENT_URL}/shopper/chat", {"session_id": session_id, "message": "cancel"}).json()
    evidence.record("resume_after_silence", response=resume_resp)

    verdict = "PASS"
    problems = []
    if orders_during_silence != orders_before:
        verdict = "FAIL"
        problems.append(f"order count changed during silence ({orders_before} -> {orders_during_silence})")
    if not resume_resp.get("done"):
        verdict = "FAIL"
        problems.append(f"expected the session to cleanly finish on cancel; got: {resume_resp}")

    evidence.flush(verdict, notes="; ".join(problems))

    assert orders_during_silence == orders_before, (
        f"SECURITY BUG: a real purchase was made while the purchase-confirmation checkpoint was awaiting a "
        f"reply with total silence ({orders_before} -> {orders_during_silence})."
    )
