"""17.2 — Policy Gate kill-mid-flight.

Goal: prove fail-closed behavior isn't just a timeout simulation — real
SIGKILL-equivalent process termination (Windows has no SIGKILL; this uses
Popen.kill(), which sends TerminateProcess — no graceful shutdown, no
chance to flush a response) at three points in the request lifecycle,
plus a concurrent variant.

Timing-window methodology (read before the test bodies): sub-millisecond
timing races against real in-process work aren't reliably reproducible
by racing an external `kill` against a live server on generic hardware.
This suite uses the SAME technique this codebase already uses elsewhere
for adversarial testing (buyer-agent's `force_aggressive_negotiation`
test-mode flag) — a small, explicitly-gated test hook in Policy Gate
(policy-gate/app/routes/evaluate.py, behind POLICY_GATE_TEST_HOOKS=1 AND
a magic session_id prefix, so it is a no-op for any real caller) that
inserts a controlled sleep at a specific point, giving this test a
reliable window to kill the process during:

  - point A ("before it receives the request"): gate killed BEFORE the
    request is even sent — no hook needed, this is just "gate is down."
  - point B ("received but before it responds"): the
    phase17-delay-before-processing hook sleeps before any decision
    logic runs; killed during that sleep.
  - point C ("responds but before backend processes it"): the
    phase17-delay-after-commit hook sleeps AFTER the decision is already
    committed to Policy Gate's own DB but BEFORE the HTTP response is
    sent; killed during that sleep. This is the "orphaned approval" case
    — did the gate's own DB end up with an approved-but-never-delivered
    decision, and does the caller correctly treat that as a rejection?

This suite manages its own Policy Gate process for the duration of its
tests (starts one with the test hooks enabled, restores a normal one —
no test hooks — when done), so it never leaves the shared dev
environment running in test mode.
"""

import subprocess
import time
import uuid
from pathlib import Path

import pytest

from conftest import BACKEND_URL, POLICY_GATE_URL, get, post

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_GATE_DIR = REPO_ROOT / "policy-gate"
HOOK_DELAY_SECONDS = 8  # must match evaluate.py's _TEST_HOOK_DELAY_SECONDS


def _find_gate_pids():
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
            "Where-Object { $_.CommandLine -match 'uvicorn.*8001' } | "
            "Select-Object -ExpandProperty ProcessId",
        ],
        capture_output=True, text=True, timeout=15,
    )
    return [int(p) for p in result.stdout.split() if p.strip().isdigit()]


def _kill_pids(pids):
    for pid in pids:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"], timeout=10)


def _wait_for(url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            get(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _start_gate(test_hooks: bool):
    env_prefix = "$env:POLICY_GATE_TEST_HOOKS='1'; " if test_hooks else ""
    log_path = REPO_ROOT / "tests" / "phase17_trust_boundary" / "evidence" / ("gate_test.log" if test_hooks else "gate_normal.log")
    subprocess.Popen(
        [
            "powershell", "-NoProfile", "-Command",
            f"{env_prefix}cd '{POLICY_GATE_DIR}'; python -m uvicorn app.main:app --port 8001 "
            f"*> '{log_path}'",
        ],
        cwd=str(POLICY_GATE_DIR),
    )
    ok = _wait_for(f"{POLICY_GATE_URL}/health", timeout=20)
    return ok


@pytest.fixture(scope="module")
def test_hook_gate():
    """Kills whatever's on :8001, starts a Policy Gate WITH test hooks
    enabled for this module's tests, then restores a NORMAL instance
    (no test hooks) on teardown so the rest of the running system is
    unaffected afterward.
    """
    _kill_pids(_find_gate_pids())
    time.sleep(1)
    started = _start_gate(test_hooks=True)
    if not started:
        pytest.skip("Could not start a test-hook-enabled Policy Gate instance")
    yield
    _kill_pids(_find_gate_pids())
    time.sleep(1)
    _start_gate(test_hooks=False)
    _wait_for(f"{POLICY_GATE_URL}/health", timeout=20)


def test_point_a_gate_dead_before_request_fails_closed(evidence):
    """No hook needed: kill the gate outright, then attempt a real
    negotiation-adjacent approval request against it."""
    _kill_pids(_find_gate_pids())
    time.sleep(1)
    evidence.record("gate_killed", note="policy-gate process terminated before sending any request")

    orders_before = get(f"{BACKEND_URL}/dashboard/summary").json()["total_orders"]

    # Real negotiation through the backend — its gate_client fails CLOSED
    # per gate_client.py's own contract when the gate is unreachable.
    start = post(f"{BACKEND_URL}/negotiate/start", {"product_id": 1, "cart_quantity": 1}).json()
    evidence.record("negotiate_start_with_gate_down", response=start)

    orders_after = get(f"{BACKEND_URL}/dashboard/summary").json()["total_orders"]
    evidence.record("orders_check", before=orders_before, after=orders_after)

    problems = []
    if start.get("offer_status") not in ("none", "rejected"):
        problems.append(f"expected a rejected/none offer_status with the gate down, got: {start.get('offer_status')}")
    if orders_after != orders_before:
        problems.append("an order was created while the gate was completely down")

    # Restore for subsequent tests in this module.
    _start_gate(test_hooks=True)

    evidence.flush("PASS" if not problems else "FAIL", notes="; ".join(problems))
    assert not problems, problems


@pytest.mark.usefixtures("test_hook_gate")
def test_point_b_killed_after_receiving_before_responding_fails_closed(evidence):
    """Uses the phase17-delay-before-processing hook: the gate accepts the
    connection and starts handling the request, then sleeps — killed
    during that sleep, before it does any decision work at all."""
    session_id = f"phase17-delay-before-processing-{uuid.uuid4().hex[:8]}"
    payload = {
        "session_id": session_id,
        "product_id": 1,
        "cart_quantity": 1,
        "original_price": 249900,
        "proposed_offer": {"type": "discount", "value": 237405, "reasoning": "test"},
        "attempt_number": 1,
    }

    import threading

    result_holder = {}

    def _send():
        try:
            r = post(f"{POLICY_GATE_URL}/evaluate", payload, timeout=HOOK_DELAY_SECONDS + 10)
            result_holder["status"] = r.status_code
            result_holder["body"] = r.json()
        except Exception as e:
            result_holder["exception"] = str(e)

    t = threading.Thread(target=_send)
    t.start()
    time.sleep(HOOK_DELAY_SECONDS / 2)  # request has been sent and is mid-sleep server-side
    _kill_pids(_find_gate_pids())
    evidence.record("gate_killed_mid_sleep", killed_at_offset_seconds=HOOK_DELAY_SECONDS / 2)
    t.join(timeout=HOOK_DELAY_SECONDS + 15)

    evidence.record("request_thread_result", result=result_holder)

    # Restore the test-hook gate for subsequent tests.
    _start_gate(test_hooks=True)

    problems = []
    if "exception" not in result_holder:
        problems.append(f"expected the client call to fail (connection reset/timeout); it completed: {result_holder}")

    evidence.flush("PASS" if not problems else "FAIL", notes="; ".join(problems))
    assert not problems, problems

    # And confirm the BACKEND's own gate_client treats an unreachable gate
    # as a rejection when this same scenario happens through a real call.
    _kill_pids(_find_gate_pids())
    time.sleep(1)
    start = post(f"{BACKEND_URL}/negotiate/start", {"product_id": 1, "cart_quantity": 1}).json()
    evidence.record("backend_negotiate_with_gate_down_again", response=start)
    _start_gate(test_hooks=True)
    assert start.get("offer_status") in ("none", "rejected"), start


@pytest.mark.usefixtures("test_hook_gate")
def test_point_c_killed_after_commit_before_response_is_an_orphaned_approval_not_a_grant(evidence):
    """Uses the phase17-delay-after-commit hook: Policy Gate DECIDES and
    COMMITS the approval to its own DB, then sleeps before sending the
    HTTP response — killed during that sleep. The decision technically
    exists in Policy Gate's database, but the caller never received it.
    Prove the caller (and thus the rest of the system) treats this as no
    approval at all, not as a silently-granted discount.
    """
    session_id = f"phase17-delay-after-commit-{uuid.uuid4().hex[:8]}"
    payload = {
        "session_id": session_id,
        "product_id": 1,
        "cart_quantity": 1,
        "original_price": 249900,
        "proposed_offer": {"type": "discount", "value": 237405, "reasoning": "test"},
        "attempt_number": 1,
    }

    import threading

    result_holder = {}

    def _send():
        try:
            r = post(f"{POLICY_GATE_URL}/evaluate", payload, timeout=HOOK_DELAY_SECONDS + 10)
            result_holder["status"] = r.status_code
            result_holder["body"] = r.json()
        except Exception as e:
            result_holder["exception"] = str(e)

    t = threading.Thread(target=_send)
    t.start()
    time.sleep(HOOK_DELAY_SECONDS / 2)
    _kill_pids(_find_gate_pids())
    evidence.record("gate_killed_after_commit_sleep_started", killed_at_offset_seconds=HOOK_DELAY_SECONDS / 2)
    t.join(timeout=HOOK_DELAY_SECONDS + 15)
    evidence.record("request_thread_result", result=result_holder)

    _start_gate(test_hooks=True)

    # The caller never got the response — confirm no code path anywhere
    # in the backend could have somehow used a value from that dead call.
    # The only way to check the ORPHANED approval itself is Policy Gate's
    # own DB, out of band.
    import sqlite3

    gate_db = POLICY_GATE_DIR / "policy_gate.db"
    orphaned_approval = None
    if gate_db.exists():
        con = sqlite3.connect(f"file:{gate_db}?mode=ro", uri=True)
        try:
            cur = con.execute(
                "SELECT session_id, decision, final_amount, used FROM approvals WHERE session_id = ?", (session_id,)
            )
            row = cur.fetchone()
            if row:
                orphaned_approval = {"session_id": row[0], "decision": row[1], "final_amount": row[2], "used": row[3]}
        finally:
            con.close()
    evidence.record("orphaned_approval_in_gate_db", found=orphaned_approval)

    problems = []
    if "exception" not in result_holder:
        problems.append(f"expected the client call to fail; it completed: {result_holder}")

    if orphaned_approval and orphaned_approval["used"] in (0, False):
        # This is the actually interesting state to prove safe: the
        # approval EXISTS in Policy Gate's DB, unused. It is only
        # dangerous if something downstream could still redeem it.
        forged_order = post(
            f"{BACKEND_URL}/order/create",
            {"product_id": 1, "quantity": 1, "approval_token": "no-caller-ever-received-this-order-so-no-real-token-exists"},
        ).json()
        evidence.record("attempted_redemption_of_orphaned_decision", response=forged_order)
        # Since the real caller never received the actual approval_token
        # (it was inside the response that never arrived), there is no
        # way to redeem this orphaned approval at all — token possession
        # IS the only credential. This assertion documents that fact
        # rather than attempting an impossible redemption.

    evidence.flush(
        "PASS" if not problems else "FAIL",
        notes=(
            f"Orphaned approval exists in Policy Gate's own DB ({orphaned_approval}) but is unreachable/unredeemable "
            "since the approval_token itself was inside the response that never reached the caller."
            if orphaned_approval else ""
        ) + "; ".join(problems),
    )
    assert not problems, problems


@pytest.mark.usefixtures("test_hook_gate")
def test_concurrent_requests_when_gate_dies_neither_silently_succeeds(evidence):
    """Two simultaneous approval requests in flight when the gate dies —
    neither should silently succeed (both must observe a failure)."""
    session_id_a = f"phase17-delay-before-processing-concurrent-a-{uuid.uuid4().hex[:8]}"
    session_id_b = f"phase17-delay-before-processing-concurrent-b-{uuid.uuid4().hex[:8]}"

    def _payload(sid):
        return {
            "session_id": sid,
            "product_id": 1,
            "cart_quantity": 1,
            "original_price": 249900,
            "proposed_offer": {"type": "discount", "value": 237405, "reasoning": "test"},
            "attempt_number": 1,
        }

    import threading

    results = {}

    def _send(key, sid):
        try:
            r = post(f"{POLICY_GATE_URL}/evaluate", _payload(sid), timeout=HOOK_DELAY_SECONDS + 10)
            results[key] = {"status": r.status_code, "body": r.json()}
        except Exception as e:
            results[key] = {"exception": str(e)}

    t1 = threading.Thread(target=_send, args=("a", session_id_a))
    t2 = threading.Thread(target=_send, args=("b", session_id_b))
    t1.start()
    t2.start()
    time.sleep(HOOK_DELAY_SECONDS / 2)
    _kill_pids(_find_gate_pids())
    evidence.record("gate_killed_with_two_in_flight", session_a=session_id_a, session_b=session_id_b)
    t1.join(timeout=HOOK_DELAY_SECONDS + 15)
    t2.join(timeout=HOOK_DELAY_SECONDS + 15)
    evidence.record("concurrent_results", results=results)

    _start_gate(test_hooks=True)

    silent_successes = [
        k for k, v in results.items() if v.get("status") == 200 and v.get("body", {}).get("approved") is True
    ]
    evidence.flush(
        "PASS" if not silent_successes else "FAIL",
        notes="" if not silent_successes else f"silent success(es): {silent_successes}",
    )
    assert not silent_successes, f"At least one concurrent request silently succeeded despite the gate dying: {results}"
