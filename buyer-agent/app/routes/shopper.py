"""Phase 10, Part C: the interactive shopper-facing interface that lets a
real PERSON drive this buyer agent turn by turn instead of it running
fully autonomously (that's still what the CLI, app/main.py, does).

Mirrors the seller's own /negotiate/start + /negotiate/message pattern
(backend/app/routes/negotiation.py) — same interrupt()/Command(resume=...)
idiom, same "check snapshot.next to know if we're paused" check — applied
here to the buyer agent's own graph instead. Not imported from there;
independently written, matching this whole client's existing rule.
"""

import threading
import time
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from app.graph.graph import buyer_graph

router = APIRouter(prefix="/shopper")

# Phase 6 (checkpoint/session safety) — independently written mirror of
# the seller side's identical fix (backend/app/routes/negotiation.py) —
# buyer_graph's MemorySaver holds every paused shopping session in
# process memory indefinitely with no built-in expiry; an abandoned
# /shopper/start that's never followed by /shopper/chat leaks memory
# forever, and a deployment restart silently loses all in-flight state
# (a genuine, accepted limit of MemorySaver for this demo deployment —
# a real production deployment would need a persistent checkpointer, not
# a TTL bolted onto the in-memory one). This sweep bounds memory growth
# and gives a stale resume a clear, honest error instead of either
# resuming ancient state or a confusing post-restart 404.
SESSION_MAX_AGE_SECONDS = 30 * 60
_session_created_at: dict[str, float] = {}
_session_tracking_guard = threading.Lock()


def _mark_session_created(session_id: str) -> None:
    with _session_tracking_guard:
        _session_created_at[session_id] = time.monotonic()


def _session_is_expired(session_id: str) -> bool:
    with _session_tracking_guard:
        created = _session_created_at.get(session_id)
    return created is not None and (time.monotonic() - created) > SESSION_MAX_AGE_SECONDS


def _sweep_expired_sessions() -> None:
    now = time.monotonic()
    with _session_tracking_guard:
        expired = [sid for sid, created in _session_created_at.items() if now - created > SESSION_MAX_AGE_SECONDS]
        for sid in expired:
            del _session_created_at[sid]
    for sid in expired:
        try:
            buyer_graph.checkpointer.delete_thread(sid)
        except Exception:
            pass  # best-effort


class StartRequest(BaseModel):
    goal: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ShopperSessionStatus(BaseModel):
    session_id: str
    exists: bool
    expired: bool
    resumable: bool
    created_at: Optional[float] = None
    expires_at: Optional[float] = None
    session_max_age_seconds: int


class ShopperResponse(BaseModel):
    session_id: str
    # None once the session is finished (done=True) — otherwise which
    # checkpoint the graph is currently paused at.
    awaiting: Optional[Literal["negotiate_checkpoint", "purchase_confirmation"]] = None
    message: str
    done: bool


def _thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _build_response(session_id: str, result: dict, config: dict) -> ShopperResponse:
    snapshot = buyer_graph.get_state(config)
    if snapshot.next:
        awaiting = snapshot.next[0]  # "await_negotiate_checkpoint" | "await_purchase_confirmation"
        label = "negotiate_checkpoint" if awaiting == "await_negotiate_checkpoint" else "purchase_confirmation"
        return ShopperResponse(session_id=session_id, awaiting=label, message=result.get("pending_message", ""), done=False)
    return ShopperResponse(session_id=session_id, awaiting=None, message=result.get("outcome", ""), done=True)


@router.post("/start", response_model=ShopperResponse)
def start_shopping(payload: StartRequest):
    _sweep_expired_sessions()
    session_id = str(uuid.uuid4())
    _mark_session_created(session_id)
    initial_state = {
        "goal": payload.goal,
        "force_aggressive_negotiation": False,
        "discovered_products": [],
        "match_found": False,
        "chosen_product": None,
        "chosen_quantity": 1,
        "should_negotiate": False,
        "proposed_type": None,
        "proposed_value": None,
        "target_budget": None,
        "negotiation_attempt": 0,
        "negotiation_result": None,
        "offer_status": None,
        "pending_message": "",
        "purchase_decision": None,
        "purchase_terms": None,
        "pay_result": None,
        "outcome": "",
    }
    config = _thread_config(session_id)
    result = buyer_graph.invoke(initial_state, config=config)
    return _build_response(session_id, result, config)


@router.post("/chat", response_model=ShopperResponse)
def shopper_chat(payload: ChatRequest):
    # Same ordering note as the seller side: check this session's own
    # expiry BEFORE sweeping, or the sweep clears its tracking entry
    # first and this check always reads "not tracked."
    if _session_is_expired(payload.session_id):
        raise HTTPException(status_code=410, detail="This shopping session has expired (30 minutes of inactivity). Start a new one.")
    _sweep_expired_sessions()
    config = _thread_config(payload.session_id)
    snapshot = buyer_graph.get_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Shopping session not found")
    if not snapshot.next:
        raise HTTPException(status_code=400, detail="This shopping session has already finished")

    result = buyer_graph.invoke(Command(resume=payload.message), config=config)
    return _build_response(payload.session_id, result, config)


# Mirrors backend/app/routes/negotiation.py's GET /negotiate/{id}/status —
# read-only visibility into the same in-memory tracking dict above, no new
# state, no decision-logic change.
@router.get("/{session_id}/status", response_model=ShopperSessionStatus)
def get_shopper_status(session_id: str):
    with _session_tracking_guard:
        created = _session_created_at.get(session_id)

    if created is None:
        return ShopperSessionStatus(
            session_id=session_id, exists=False, expired=False, resumable=False, session_max_age_seconds=SESSION_MAX_AGE_SECONDS
        )

    now = time.monotonic()
    expired = (now - created) > SESSION_MAX_AGE_SECONDS
    wall_now = time.time()
    created_wall = wall_now - (now - created)

    resumable = False
    if not expired:
        try:
            snapshot = buyer_graph.get_state(_thread_config(session_id))
            resumable = bool(snapshot.values) and bool(snapshot.next)
        except Exception:
            resumable = False

    return ShopperSessionStatus(
        session_id=session_id,
        exists=True,
        expired=expired,
        resumable=resumable,
        created_at=created_wall,
        expires_at=created_wall + SESSION_MAX_AGE_SECONDS,
        session_max_age_seconds=SESSION_MAX_AGE_SECONDS,
    )
