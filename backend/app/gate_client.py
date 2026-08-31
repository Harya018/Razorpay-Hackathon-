"""The ONLY code in this backend that talks to the policy-gate over HTTP.
Used by the seller agent (human negotiation), /order/create, and the
agent-commerce routes alike — none of them may reimplement this call or
trust a gate response that didn't come through here.
"""

import logging
import threading
import time
from collections import deque
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

# Rolling in-memory stats over real /evaluate + /verify calls, for the
# dashboard's Policy Gate Status panel — approve/deny counts and average
# latency are measured from ACTUAL network round trips through this
# module, not estimated. Bounded deque + a lock since FastAPI's sync
# routes run in a threadpool and could genuinely race on this otherwise
# (this codebase has already found one real TOCTOU race in policy-gate's
# own /verify — no reason to introduce a sloppier one here, even in a
# side-channel that only feeds a UI).
_STATS_WINDOW = 500
_stats_lock = threading.Lock()
_call_log: deque = deque(maxlen=_STATS_WINDOW)
_process_started_at = time.time()


def _record_call(outcome: str, elapsed_ms: float) -> None:
    with _stats_lock:
        _call_log.append({"outcome": outcome, "elapsed_ms": elapsed_ms, "ts": time.time()})


def get_gate_call_stats() -> dict:
    """outcome is one of "approved" / "denied" / "unreachable" — counted
    over whatever's currently in the rolling window (up to the last
    _STATS_WINDOW real calls made by THIS backend process since it last
    started; resets on restart, which is an honest reflection of "calls
    this session has actually made," not a persisted all-time counter).
    """
    with _stats_lock:
        calls = list(_call_log)
    approved = sum(1 for c in calls if c["outcome"] == "approved")
    denied = sum(1 for c in calls if c["outcome"] == "denied")
    unreachable = sum(1 for c in calls if c["outcome"] == "unreachable")
    reached = [c for c in calls if c["outcome"] != "unreachable"]
    avg_latency_ms = round(sum(c["elapsed_ms"] for c in reached) / len(reached), 1) if reached else None
    last_call_at = calls[-1]["ts"] if calls else None
    return {
        "total_calls": len(calls),
        "approved": approved,
        "denied": denied,
        "unreachable": unreachable,
        "avg_latency_ms": avg_latency_ms,
        "last_call_at": last_call_at,
        "process_uptime_seconds": round(time.time() - _process_started_at, 1),
    }

# Phase 14 — a clean, dashboard-presentable reason code. The dashboard's
# event feed (_agent_headline / _human_headline) shows `reason` directly
# to a merchant; the raw exception text (connection refused, DNS failure,
# etc.) is real and useful, but belongs in a log line for an engineer, not
# in a headline a merchant reads during a live demo. Same fail-CLOSED
# behavior as before — only the presentation of WHY changed.
POLICY_GATE_UNREACHABLE_REASON = "policy_gate_unreachable"


def evaluate(
    session_id: str,
    product_id: int,
    cart_quantity: int,
    original_price: int,
    proposed_offer: dict,
    attempt_number: int,
    requester_id: Optional[str] = None,
) -> dict:
    request_payload = {
        "session_id": session_id,
        "product_id": product_id,
        "cart_quantity": cart_quantity,
        "original_price": original_price,
        "proposed_offer": proposed_offer,
        "attempt_number": attempt_number,
        "requester_id": requester_id,
    }
    start = time.monotonic()
    try:
        response = requests.post(f"{settings.POLICY_GATE_URL}/evaluate", json=request_payload, timeout=5)
        response.raise_for_status()
        result = response.json()
        _record_call("approved" if result.get("approved") else "denied", (time.monotonic() - start) * 1000)
        return result
    except requests.RequestException as e:
        # Fail CLOSED: if the gate can't be reached, that's a rejection, not
        # an approval — we never assume "yes" when we can't confirm it.
        logger.warning("policy-gate unreachable during /evaluate: %s", e)
        _record_call("unreachable", (time.monotonic() - start) * 1000)
        return {
            "approved": False,
            "reason": POLICY_GATE_UNREACHABLE_REASON,
            "max_allowed": None,
            "approval_token": None,
            "final_terms": None,
        }


def verify_token(
    approval_token: str,
    product_id: int,
    cart_quantity: int,
    requester_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    start = time.monotonic()
    try:
        response = requests.post(
            f"{settings.POLICY_GATE_URL}/verify",
            json={
                "approval_token": approval_token,
                "product_id": product_id,
                "cart_quantity": cart_quantity,
                "requester_id": requester_id,
                "session_id": session_id,
            },
            timeout=5,
        )
        response.raise_for_status()
        result = response.json()
        _record_call("approved" if result.get("valid") else "denied", (time.monotonic() - start) * 1000)
        return result
    except requests.RequestException as e:
        # Fail CLOSED — see evaluate() above.
        logger.warning("policy-gate unreachable during /verify: %s", e)
        _record_call("unreachable", (time.monotonic() - start) * 1000)
        return {"valid": False, "reason": POLICY_GATE_UNREACHABLE_REASON}
