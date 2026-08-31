"""Phase 10, Part C: the interactive shopper-facing interface that lets a
real PERSON drive this buyer agent turn by turn instead of it running
fully autonomously (that's still what the CLI, app/main.py, does).

Mirrors the seller's own /negotiate/start + /negotiate/message pattern
(backend/app/routes/negotiation.py) — same interrupt()/Command(resume=...)
idiom, same "check snapshot.next to know if we're paused" check — applied
here to the buyer agent's own graph instead. Not imported from there;
independently written, matching this whole client's existing rule.
"""

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from app.graph.graph import buyer_graph

router = APIRouter(prefix="/shopper")


class StartRequest(BaseModel):
    goal: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


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
    session_id = str(uuid.uuid4())
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
    config = _thread_config(payload.session_id)
    snapshot = buyer_graph.get_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Shopping session not found")
    if not snapshot.next:
        raise HTTPException(status_code=400, detail="This shopping session has already finished")

    result = buyer_graph.invoke(Command(resume=payload.message), config=config)
    return _build_response(payload.session_id, result, config)
