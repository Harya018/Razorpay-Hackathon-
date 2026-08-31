"""Phase 14, demo beat 1 — "policy gate rejects a ceiling-breaking ask."

Standalone, one-command, HTTP-only (own venv, no imports from backend
source). Drives a real negotiation past the merchant's actual discount
ceiling via the deterministic agent channel (no LLM latency in the
decision path, so this stays fast and reliable under pitch-day pressure),
then reads the SAME event back off the merchant dashboard's own event
feed — proving the rejection is visible there, with the specific rule
that triggered it, not just narrated by this script.

Run: python demo_ceiling_rejection.py [--base-url http://127.0.0.1:8010]
"""

import argparse
import sys
import time

import httpx
import uuid

STEP_PAUSE = 0.0  # set >0 if you want artificial pacing between steps while narrating live


def _step(n: int, total: int, message: str) -> None:
    print(f"[{n}/{total}] {message}")
    if STEP_PAUSE:
        time.sleep(STEP_PAUSE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo: policy gate rejects a ceiling-breaking discount ask")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    base = args.base_url

    t0 = time.time()
    total_steps = 5

    with httpx.Client(timeout=15) as client:
        _step(1, total_steps, "Registering a fresh buyer agent...")
        buyer_id = f"demo-ceiling-{uuid.uuid4().hex[:8]}"
        resp = client.post(f"{base}/agent/v1/register", json={"buyer_agent_id": buyer_id})
        resp.raise_for_status()
        api_key = resp.json()["api_key"]
        headers = {"Authorization": f"Bearer {api_key}"}
        print(f"    buyer_agent_id = {buyer_id}")

        _step(2, total_steps, "Fetching catalog and picking a product with a known discount ceiling...")
        catalog = client.get(f"{base}/agent/v1/catalog").json()
        product = catalog[0]  # Wireless Headphones — 10% max_discount_pct, per merchant_rules.py's PRODUCT_RULES
        listed_total = product["price"]
        print(f"    product = {product['name']!r}, listed price = Rs {listed_total / 100:.2f}")

        _step(3, total_steps, "Buyer agent pushes WAY past the ceiling — asking for 60% off...")
        ask_value = round(listed_total * 0.40)  # i.e. asking to pay only 40% of list price = 60% off
        ask_pct = (listed_total - ask_value) / listed_total * 100
        print(f"    requested total = Rs {ask_value / 100:.2f}  ({ask_pct:.0f}% off)")

        neg_resp = client.post(
            f"{base}/agent/v1/negotiate",
            headers=headers,
            json={
                "product_id": product["id"],
                "quantity": 1,
                "buyer_agent_id": buyer_id,
                "proposed_terms": {"type": "discount", "value": ask_value},
            },
        )
        neg_resp.raise_for_status()
        neg_body = neg_resp.json()

        _step(4, total_steps, "Checking the policy gate's own decision (not this script's opinion of it)...")
        approved = neg_body.get("approved")
        reason = neg_body.get("reason")
        max_allowed = neg_body.get("max_allowed")

        if approved:
            print("\n    !!! UNEXPECTED: the gate APPROVED an offer past the documented ceiling. This is a real bug, not a demo. !!!")
            return 1

        max_allowed_pct = (listed_total - max_allowed) / listed_total * 100 if max_allowed else None
        print(f"    REJECTED — reason: {reason}")
        if max_allowed is not None:
            print(
                f"    The specific rule: this product's real ceiling allows a final price no lower than "
                f"Rs {max_allowed / 100:.2f} ({max_allowed_pct:.1f}% off) — the ask of Rs {ask_value / 100:.2f} "
                f"({ask_pct:.0f}% off) was below that floor, not just \"denied.\""
            )

        _step(5, total_steps, "Confirming this exact rejection is visible on the merchant dashboard's live event feed...")
        found_on_dashboard = False
        for attempt in range(4):  # up to ~2s of polling, matching the dashboard's own ~1.5s SSE poll interval
            activity = client.get(f"{base}/dashboard/agent-activity", params={"limit": 10}).json()
            for group in activity:
                decision = group.get("gate_decision") or {}
                if group.get("buyer_agent_id") == buyer_id and decision.get("reason") == reason:
                    found_on_dashboard = True
                    print(f"    Found on dashboard: {group['headline']!r}")
                    break
            if found_on_dashboard:
                break
            time.sleep(0.5)

        if not found_on_dashboard:
            print("    WARNING: did not find this event on GET /dashboard/agent-activity within ~2s — check the dashboard is reading from the same database this script hit.")

    elapsed = time.time() - t0
    print(f"\n=== DONE in {elapsed:.1f}s — {'PASS' if (not approved and found_on_dashboard) else 'CHECK OUTPUT ABOVE'} ===\n")
    return 0 if (not approved and found_on_dashboard) else 1


if __name__ == "__main__":
    sys.exit(main())
