import json
import threading
import time
import uuid

from fastapi import APIRouter, Header, HTTPException
from langgraph.types import Command

from app.agent.graph import negotiation_graph
from app.database import SessionLocal
from app.idempotency import run_idempotent
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.schemas.negotiation import (
    AuditLogEntry,
    NegotiateMessageRequest,
    NegotiateMessageResponse,
    NegotiateStartRequest,
    NegotiateStartResponse,
    NegotiationSessionStatus,
)

router = APIRouter()


def _thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


# Phase 6 (checkpoint/session safety) — MemorySaver holds every paused
# negotiation's full state IN PROCESS MEMORY, indefinitely, with no
# built-in expiry: a shopper who opens a negotiation and never replies
# leaves it consuming memory forever, and a deployment restart silently
# loses every in-flight session (MemorySaver has no persistence — this is
# a genuine, accepted architecture limit for THIS demo deployment, not
# something a session-expiry sweep can fix; a real production deployment
# would need a persistent checkpointer, e.g. langgraph-checkpoint-postgres,
# not just a TTL on top of the in-memory one). What THIS sweep does fix:
# bounding memory growth from abandoned sessions, and giving a stale
# resume attempt a clear, honest error instead of either silently
# succeeding on ancient state or (post-restart) a confusing 404 that looks
# like a bug rather than "this session's process has restarted since."
SESSION_MAX_AGE_SECONDS = 30 * 60  # 30 minutes — long enough for a real negotiation, short enough to bound demo memory growth
_session_created_at: dict[str, float] = {}
_session_tracking_guard = threading.Lock()


def _mark_session_created(session_id: str) -> None:
    with _session_tracking_guard:
        _session_created_at[session_id] = time.monotonic()


def _sweep_expired_sessions() -> None:
    """Opportunistic sweep — runs on every /negotiate/start and
    /negotiate/message call rather than a background thread, so this adds
    no new infrastructure (no scheduler, no extra process) while still
    keeping memory bounded under real usage. Deletes both this module's
    own bookkeeping AND the checkpointer's actual stored state via
    delete_thread(), so an expired session's memory is genuinely
    reclaimed, not just hidden behind an error message.
    """
    now = time.monotonic()
    with _session_tracking_guard:
        expired = [sid for sid, created in _session_created_at.items() if now - created > SESSION_MAX_AGE_SECONDS]
        for sid in expired:
            del _session_created_at[sid]
            _session_locks.pop(sid, None)
    for sid in expired:
        try:
            negotiation_graph.checkpointer.delete_thread(sid)
        except Exception:
            pass  # best-effort — an already-gone/unsupported thread is not an error worth surfacing


def _session_is_expired(session_id: str) -> bool:
    with _session_tracking_guard:
        created = _session_created_at.get(session_id)
    # A session this process never saw created (e.g. a restart since it
    # started) isn't "expired" in the tracked sense — its checkpoint state
    # is just gone; get_state()'s own empty-snapshot check below already
    # produces a clear "session not found" for that case.
    return created is not None and (time.monotonic() - created) > SESSION_MAX_AGE_SECONDS


# Red-team-confirmed race (red-team-agent's concurrent_race.py, "Same-
# session double negotiation"): send_message is a sync route, so FastAPI
# runs concurrent calls on separate threadpool threads; MemorySaver has no
# per-thread_id locking of its own, so two concurrent /negotiate/message
# calls for the SAME session_id could both read the same starting
# checkpoint via get_state() and both independently invoke(resume=...)
# from it — reproduced live as two responses both reporting the identical
# turn_count, i.e. two concurrent browser retries could grant an extra,
# unearned discount-ladder rung. Fixed the same way the two other
# check-then-write races in this codebase were (see policy-gate/app/
# routes/evaluate.py's /verify and backend's /pay): serialize the
# read-state-then-resume sequence for one session_id behind its own lock —
# a per-session_id dict of threading.Lock, guarded by one small lock for
# the dict's own mutation (the standard striped-locking pattern). Other
# sessions are completely unaffected — this only serializes concurrent
# requests that share a session_id, which is already a single, sequential
# conversation by design. Entries ARE evicted now (Phase 6) — see
# _sweep_expired_sessions above, which removes a session's lock alongside
# its checkpoint state once it's past SESSION_MAX_AGE_SECONDS — so this
# dict stays bounded by "sessions active within the expiry window," not
# "every session ever created since process start."
_session_locks: dict[str, threading.Lock] = {}
_session_locks_guard = threading.Lock()


def _lock_for_session(session_id: str) -> threading.Lock:
    with _session_locks_guard:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _session_locks[session_id] = lock
        return lock


def _latest_assistant_message(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg["role"] == "assistant":
            return msg["content"]
    return ""


@router.post("/negotiate/start", response_model=NegotiateStartResponse)
def start_negotiation(payload: NegotiateStartRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    _sweep_expired_sessions()
    db = SessionLocal()
    try:
        def create_response() -> dict:
            product = db.get(Product, payload.product_id)
            if product is None:
                raise HTTPException(status_code=404, detail="Product not found")
            session_id = str(uuid.uuid4())
            _mark_session_created(session_id)
            initial_state = {
                "session_id": session_id,
                "product_id": payload.product_id,
                "cart_quantity": payload.cart_quantity,
                "original_price": product.price,
                "hesitation_signal": "manual_trigger",
                "conversation_history": [],
                "proposed_offer": None,
                "offer_status": "none",
                "turn_count": 0,
                "approval_token": None,
            }
            result = negotiation_graph.invoke(initial_state, config=_thread_config(session_id))
            return {
                "session_id": session_id,
                "message": _latest_assistant_message(result["conversation_history"]),
                "proposed_offer": result.get("proposed_offer"),
                "offer_status": result["offer_status"],
                "turn_count": result["turn_count"],
            }

        response = run_idempotent(db, "negotiate_start", idempotency_key, payload.model_dump(), create_response)
        return NegotiateStartResponse(**response)
    finally:
        db.close()


@router.post("/negotiate/message", response_model=NegotiateMessageResponse)
def send_message(payload: NegotiateMessageRequest):
    # Order matters: check THIS session's own expiry before sweeping —
    # the sweep would otherwise delete this exact session's tracking
    # entry first, making the expiry check below always read "not
    # tracked" and fall through to a plain 404 instead of the clearer,
    # honest "this expired" message.
    if _session_is_expired(payload.session_id):
        raise HTTPException(
            status_code=410,
            detail="This negotiation session has expired (30 minutes of inactivity). Start a new one.",
        )
    _sweep_expired_sessions()
    config = _thread_config(payload.session_id)
    with _lock_for_session(payload.session_id):
        snapshot = negotiation_graph.get_state(config)
        if not snapshot.values:
            raise HTTPException(status_code=404, detail="Negotiation session not found")
        if not snapshot.next:
            raise HTTPException(status_code=400, detail="Negotiation already closed")

        result = negotiation_graph.invoke(Command(resume=payload.user_message), config=config)
        closed = not bool(negotiation_graph.get_state(config).next)
    handoff = closed and result["offer_status"] == "accepted"

    checkout_amount = None
    approval_token = None
    if handoff:
        offer = result.get("proposed_offer")
        if offer and offer.get("value") is not None:
            checkout_amount = offer["value"]
        approval_token = result.get("approval_token")

    return NegotiateMessageResponse(
        session_id=payload.session_id,
        message=_latest_assistant_message(result["conversation_history"]),
        proposed_offer=result.get("proposed_offer"),
        offer_status=result["offer_status"],
        turn_count=result["turn_count"],
        closed=closed,
        handoff=handoff,
        checkout_amount=checkout_amount,
        approval_token=approval_token,
    )


@router.get("/negotiate/{session_id}/audit", response_model=list[AuditLogEntry])
def get_negotiation_audit(session_id: str):
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.created_at, AuditLog.id).all()
        entries = []
        for row in rows:
            try:
                payload = json.loads(row.payload) if row.payload else {}
            except (TypeError, json.JSONDecodeError):
                continue
            if payload.get("session_id") != session_id:
                continue
            entries.append(
                AuditLogEntry(id=row.id, event_type=row.event_type, payload=payload, created_at=row.created_at, order_id=row.order_id)
            )
        return entries
    finally:
        db.close()


# Read-only visibility into the same in-memory expiry tracking
# _sweep_expired_sessions already enforces as a side effect on
# /negotiate/message (see SESSION_MAX_AGE_SECONDS above) — added
# specifically so the frontend's "LangGraph Session" technical card can
# show real checkpoint/resumability status instead of only ever
# discovering expiry the hard way (a 410 from an actual message attempt).
# Exposes no new state and changes no decision logic — same tracking
# dict, same 30-minute rule, just now queryable.
@router.get("/negotiate/{session_id}/status", response_model=NegotiationSessionStatus)
def get_negotiation_status(session_id: str):
    with _session_tracking_guard:
        created = _session_created_at.get(session_id)

    if created is None:
        return NegotiationSessionStatus(
            session_id=session_id,
            exists=False,
            expired=False,
            resumable=False,
            session_max_age_seconds=SESSION_MAX_AGE_SECONDS,
        )

    now = time.monotonic()
    expired = (now - created) > SESSION_MAX_AGE_SECONDS
    wall_now = time.time()
    created_wall = wall_now - (now - created)

    resumable = False
    if not expired:
        try:
            snapshot = negotiation_graph.get_state(_thread_config(session_id))
            resumable = bool(snapshot.values) and bool(snapshot.next)
        except Exception:
            resumable = False

    return NegotiationSessionStatus(
        session_id=session_id,
        exists=True,
        expired=expired,
        resumable=resumable,
        created_at=created_wall,
        expires_at=created_wall + SESSION_MAX_AGE_SECONDS,
        session_max_age_seconds=SESSION_MAX_AGE_SECONDS,
    )
