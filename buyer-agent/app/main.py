import argparse
import sys
import uuid

from langgraph.types import Command

from app.graph.graph import buyer_graph


def _thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def main():
    # Windows terminals often default stdout to a codepage (e.g. cp1252)
    # that can't encode the rupee sign this agent prints — reconfigure to
    # UTF-8 rather than let a display-only issue crash a real purchase.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Autonomous buyer agent")
    parser.add_argument("goal", help="Natural-language shopping goal, e.g. 'a warm-toned lamp under 3500 rupees'")
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Test harness only: force an aggressive negotiation ask to exercise the gate's rejection path",
    )
    args = parser.parse_args()

    initial_state = {
        "goal": args.goal,
        "force_aggressive_negotiation": args.aggressive,
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

    # Phase 10, Part C added two human-in-the-loop pauses to this graph
    # (a real person answers them via POST /shopper/chat — see
    # app/server.py). This CLI stays fully autonomous, as it always has
    # been: it AUTO-RESUMES through both, always choosing "negotiate
    # more" until the ladder's last rung, then "buy" — but it prints each
    # pause as it happens, so the checkpoints firing is still visible,
    # not silently skipped.
    session_id = str(uuid.uuid4())
    config = _thread_config(session_id)
    result = buyer_graph.invoke(initial_state, config=config)

    while buyer_graph.get_state(config).next:
        awaiting = buyer_graph.get_state(config).next[0]
        print(f"\n[checkpoint: {awaiting}] {result.get('pending_message', '')}")
        if awaiting == "await_negotiate_checkpoint":
            reply = "negotiate more"
            print("  -> auto-reply (CLI is non-interactive): 'negotiate more'")
        else:
            reply = "buy"
            print("  -> auto-reply (CLI is non-interactive): 'buy'")
        result = buyer_graph.invoke(Command(resume=reply), config=config)

    print("\n=== BUYER AGENT REPORT ===")
    print(result["outcome"])
    print("===========================\n")


if __name__ == "__main__":
    main()
