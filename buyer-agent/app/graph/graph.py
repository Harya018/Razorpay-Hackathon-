from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import BuyerState

_builder = StateGraph(BuyerState)
_builder.add_node("discover", nodes.discover)
_builder.add_node("evaluate", nodes.evaluate)
_builder.add_node("_negotiate_bundle_once", nodes._negotiate_bundle_once)
_builder.add_node("negotiate_round", nodes.negotiate_round)
_builder.add_node("await_negotiate_checkpoint", nodes.await_negotiate_checkpoint)
_builder.add_node("await_purchase_confirmation", nodes.await_purchase_confirmation)
_builder.add_node("purchase", nodes.purchase)
_builder.add_node("report", nodes.report)

_builder.add_edge(START, "discover")
_builder.add_edge("discover", "evaluate")
# Every other edge is decided dynamically via Command(goto=...):
#   evaluate            -> negotiate_round | _negotiate_bundle_once | await_purchase_confirmation | report
#   _negotiate_bundle_once -> await_purchase_confirmation
#   negotiate_round      -> await_negotiate_checkpoint | await_purchase_confirmation
#   await_negotiate_checkpoint  -> negotiate_round | await_purchase_confirmation | report
#   await_purchase_confirmation -> purchase | report
_builder.add_edge("purchase", "report")
_builder.add_edge("report", END)

# Phase 10, Part C: this agent now PAUSES for a real person (via
# /shopper/chat) at up to two independent checkpoints — a checkpointer is
# required for interrupt()/Command(resume=...) to survive across separate
# HTTP requests, exactly like the seller's own negotiation_graph
# (backend/app/agent/graph.py) already does. MemorySaver is in-memory
# only (lost on process restart), matching that same seller-side
# tradeoff, not a new one introduced here.
_checkpointer = MemorySaver()
buyer_graph = _builder.compile(checkpointer=_checkpointer)
