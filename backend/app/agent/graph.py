from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.state import NegotiationState

_builder = StateGraph(NegotiationState)
_builder.add_node("assess_cart", nodes.assess_cart)
_builder.add_node("decide_to_offer", nodes.decide_to_offer)
_builder.add_node("propose_offer", nodes.propose_offer)
_builder.add_node("handle_response", nodes.handle_response)
_builder.add_node("close_negotiation", nodes.close_negotiation)

_builder.add_edge(START, "assess_cart")
_builder.add_edge("assess_cart", "decide_to_offer")
# decide_to_offer, propose_offer, and handle_response all route dynamically
# via Command(goto=...) — e.g. propose_offer can end the negotiation itself
# now, if the gate rejects with no usable fallback ceiling.
_builder.add_edge("close_negotiation", END)

# In-memory checkpointer: holds negotiation state per session_id (thread_id)
# for the lifetime of this process. Fine for a hackathon-scale single
# process; a restart loses in-flight negotiations, which is an accepted
# limitation for this phase.
_checkpointer = MemorySaver()

negotiation_graph = _builder.compile(checkpointer=_checkpointer)
