import json
import threading
import uuid

from fastapi import APIRouter, HTTPException
from langgraph.types import Command

from app.agent.graph import negotiation_graph
from app.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.schemas.negotiation import (
    AuditLogEntry,
    NegotiateMessageRequest,
    NegotiateMessageResponse,
    NegotiateStartRequest,
    NegotiateStartResponse,
)

router = APIRouter()


def _thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


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
# conversation by design. The lock dict is never evicted (one entry per
# session ever created) — an accepted scope trade-off for this same
# in-memory, single-process, restart-loses-everything deployment
# MemorySaver's own docstring already accepts.
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
def start_negotiation(payload: NegotiateStartRequest):
    db = SessionLocal()
    try:
        product = db.get(Product, payload.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        original_price = product.price
    finally:
        db.close()

    session_id = str(uuid.uuid4())
    initial_state = {
        "session_id": session_id,
        "product_id": payload.product_id,
        "cart_quantity": payload.cart_quantity,
        "original_price": original_price,
        "hesitation_signal": "manual_trigger",
        "conversation_history": [],
        "proposed_offer": None,
        "offer_status": "none",
        "turn_count": 0,
        "approval_token": None,
    }

    result = negotiation_graph.invoke(initial_state, config=_thread_config(session_id))

    return NegotiateStartResponse(
        session_id=session_id,
        message=_latest_assistant_message(result["conversation_history"]),
        proposed_offer=result.get("proposed_offer"),
        offer_status=result["offer_status"],
        turn_count=result["turn_count"],
    )


@router.post("/negotiate/message", response_model=NegotiateMessageResponse)
def send_message(payload: NegotiateMessageRequest):
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
                AuditLogEntry(id=row.id, event_type=row.event_type, payload=payload, created_at=row.created_at)
            )
        return entries
    finally:
        db.close()
