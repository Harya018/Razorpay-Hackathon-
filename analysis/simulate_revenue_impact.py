"""Revenue Impact Simulation (Phase 5).

Standalone script. Does not modify /backend, /policy-gate, /frontend, or
/buyer-agent, and is not imported by any of them — a one-way consumer of
the backend's real HTTP API only.

WHAT THIS MEASURES vs WHAT IT DOES NOT MEASURE — read this before citing
any number this script produces:

  - It measures: "if a session hits a hesitation trigger and a scripted
    reply pattern plays out, what does the REAL negotiation pipeline
    (Phase 2's seller agent + Phase 3's policy gate, actually running,
    actually called over HTTP) produce — does it convert, at what price,
    at what discount cost?"
  - It does NOT measure: whether real human shoppers actually behave like
    the scripted reply patterns here, or whether a negotiation offer
    actually changes real purchase behavior at the rate assumed. That is
    a conversion-psychology question this script has no data on and does
    not claim to answer.

The hesitation rate and cart values are SYNTHETIC — clearly stated as
assumptions, not measured production data. See README.md for the full
assumptions list and justification.

Usage:
    python simulate_revenue_impact.py [--regenerate-scenarios] [--seed 42]

Requires the backend to be running (default http://127.0.0.1:8010) with
at least one seeded product — this script calls the real
POST /negotiate/start and POST /negotiate/message endpoints (Phase 2/3's
actual code), and POST /order/create for converted sessions (Phase 1/3's
actual code). Nothing about the negotiation logic is mocked or
reimplemented here.
"""

import argparse
import json
import os
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCENARIOS_PATH = os.path.join(SCRIPT_DIR, "scenarios.json")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
REPORT_PATH = os.path.join(RESULTS_DIR, "revenue_impact_report.md")
RAW_RESULTS_PATH = os.path.join(RESULTS_DIR, "raw_results.json")

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8010")

# --------------------------------------------------------------------------
# ASSUMPTIONS — stated here in code AND repeated in README.md and the
# generated report. Do not let these numbers drift silently.
# --------------------------------------------------------------------------
DEFAULT_SESSION_COUNT = 60
DEFAULT_HESITATION_RATE = 0.35
HESITATION_RATE_JUSTIFICATION = (
    "Published e-commerce cart-abandonment studies (e.g. Baymard Institute "
    "meta-analyses) commonly cite AVERAGE abandonment in the 60-80% range "
    "across all causes (shipping cost surprises, forced account creation, "
    "just browsing, etc.) — most of that is NOT price-sensitive and would "
    "not respond to a negotiation-style intervention. This simulation "
    "assumes a deliberately more conservative 35% of sessions represent "
    "genuine, price-related hesitation that a negotiation offer could "
    "plausibly address. This is a reasonable, stated assumption for "
    "demonstration purposes — it is NOT a measured figure for this "
    "specific merchant, and no real user behavior data informs it."
)
DEFAULT_SEED = 42

PRODUCT_IDS_FALLBACK = [1, 2]  # only used if the live catalog can't be reached at generation time
QUANTITY_CHOICES = [1, 1, 1, 2, 2, 3]  # skewed toward single-unit carts

# Scripted shopper reply patterns. Deliberately varied — some accept
# immediately, some counter once or twice then accept, some reject
# outright, some counter then reject, one persona pushes aggressively
# until the attempt cap forces a close. These are FIXED strings, not
# LLM-generated — "scripted" per the phase spec, so runs are reproducible
# and every session's behavior is auditable after the fact.
PERSONA_SCRIPTS: dict[str, list[str]] = {
    "immediate_accept": [
        "Yes, that works for me — I'll take it at that price.",
    ],
    "counter_once_then_accept": [
        "Can you do a little better on the price?",
        "Okay, that works — I'll take it.",
    ],
    "counter_twice_then_accept": [
        "Is there any room to come down on the price a bit?",
        "I appreciate it, but could you sweeten it just a little more?",
        "Alright, deal — I'll go with that.",
    ],
    "immediate_reject": [
        "No thanks, not interested right now.",
    ],
    "counter_then_reject": [
        "Can you offer a bigger discount than that?",
        "That's still not quite enough for me — I'll pass, thanks anyway.",
    ],
    "push_until_cap": [
        "Can you go lower? I was hoping for a much bigger discount.",
        "Still not enough — I really need at least 25% off to make this work.",
        "Come on, meet me closer to 30% off or I'm going to walk away.",
    ],
}
PERSONA_WEIGHTS = {
    "immediate_accept": 3,
    "counter_once_then_accept": 3,
    "counter_twice_then_accept": 2,
    "immediate_reject": 2,
    "counter_then_reject": 2,
    "push_until_cap": 2,
}


def _fetch_live_catalog() -> dict[int, dict]:
    resp = requests.get(f"{BACKEND_BASE_URL}/catalog", timeout=10)
    resp.raise_for_status()
    return {p["id"]: p for p in resp.json()}


def generate_scenarios(n: int, hesitation_rate: float, seed: int) -> list[dict]:
    rng = random.Random(seed)

    try:
        catalog = _fetch_live_catalog()
        product_ids = list(catalog.keys())
    except requests.RequestException:
        product_ids = PRODUCT_IDS_FALLBACK

    if not product_ids:
        product_ids = PRODUCT_IDS_FALLBACK

    persona_pool = []
    for persona, weight in PERSONA_WEIGHTS.items():
        persona_pool.extend([persona] * weight)

    scenarios = []
    for i in range(n):
        would_hesitate = rng.random() < hesitation_rate
        scenarios.append(
            {
                "session_id": f"sim-{i + 1:03d}",
                "product_id": rng.choice(product_ids),
                "quantity": rng.choice(QUANTITY_CHOICES),
                "would_hesitate": would_hesitate,
                "shopper_persona": rng.choice(persona_pool) if would_hesitate else None,
            }
        )
    return scenarios


def load_or_generate_scenarios(n: int, hesitation_rate: float, seed: int, regenerate: bool) -> list[dict]:
    if not regenerate and os.path.exists(SCENARIOS_PATH):
        with open(SCENARIOS_PATH, encoding="utf-8") as f:
            return json.load(f)

    scenarios = generate_scenarios(n, hesitation_rate, seed)
    with open(SCENARIOS_PATH, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2)
    return scenarios


@dataclass
class SessionResult:
    session_id: str
    product_id: int
    quantity: int
    would_hesitate: bool
    shopper_persona: Optional[str]
    original_unit_price: int  # paise
    original_total_price: int  # paise
    converted: bool
    final_price: Optional[int] = None  # paise, only set if converted
    discount_given: int = 0  # paise
    negotiation_turns: int = 0
    negotiation_session_id: Optional[str] = None
    order_id: Optional[int] = None
    razorpay_order_id: Optional[str] = None
    error: Optional[str] = None
    conversation: list[dict] = field(default_factory=list)


def run_hesitating_session(session: dict, unit_price: int) -> SessionResult:
    quantity = session["quantity"]
    original_total = unit_price * quantity
    persona = session["shopper_persona"]
    script = PERSONA_SCRIPTS.get(persona, ["Yes, I'll take it."])

    result = SessionResult(
        session_id=session["session_id"],
        product_id=session["product_id"],
        quantity=quantity,
        would_hesitate=True,
        shopper_persona=persona,
        original_unit_price=unit_price,
        original_total_price=original_total,
        converted=False,
    )

    try:
        start_resp = requests.post(
            f"{BACKEND_BASE_URL}/negotiate/start",
            json={"product_id": session["product_id"], "cart_quantity": quantity},
            timeout=60,
        )
        start_resp.raise_for_status()
        start_body = start_resp.json()
    except requests.RequestException as e:
        result.error = f"negotiate/start failed: {e}"
        return result

    negotiation_session_id = start_body["session_id"]
    result.negotiation_session_id = negotiation_session_id
    result.conversation.append({"role": "assistant", "message": start_body["message"]})

    # The agent can legitimately decide NOT to open with an offer at all
    # (decide_to_offer's should_offer=False path) — the negotiation closes
    # immediately, with no interrupt ever reached, so there is no open
    # turn to reply into. Detected here as an empty opening message with
    # offer_status "none"; sending a scripted reply in this case would hit
    # the real /negotiate/message "already closed" 400 — a legitimate
    # response, but one this script should recognize as "hesitating
    # session, agent chose not to intervene, lost" rather than an error.
    if not start_body["message"] and start_body["offer_status"] == "none":
        result.negotiation_turns = 0
        return result

    closed = False
    handoff = False
    checkout_amount = None
    approval_token = None
    turn_index = 0

    while not closed and turn_index < len(script):
        reply = script[turn_index]
        result.conversation.append({"role": "user", "message": reply})
        try:
            msg_resp = requests.post(
                f"{BACKEND_BASE_URL}/negotiate/message",
                json={"session_id": negotiation_session_id, "user_message": reply},
                timeout=60,
            )
            msg_resp.raise_for_status()
            msg_body = msg_resp.json()
        except requests.RequestException as e:
            result.error = f"negotiate/message failed on turn {turn_index + 1}: {e}"
            return result

        result.conversation.append({"role": "assistant", "message": msg_body["message"]})
        closed = msg_body["closed"]
        handoff = msg_body["handoff"]
        checkout_amount = msg_body.get("checkout_amount")
        approval_token = msg_body.get("approval_token")
        turn_index += 1

    result.negotiation_turns = turn_index

    if not closed:
        # Persona's script ran out before the negotiation reached a close —
        # modeled here as the shopper abandoning mid-conversation. A real
        # and legitimate outcome, not an error.
        result.error = None
        result.converted = False
        return result

    if handoff and checkout_amount is not None:
        result.converted = True
        result.final_price = checkout_amount
        result.discount_given = max(0, original_total - checkout_amount)

        # Complete the real checkout, same as a real converted user would —
        # this is Phase 1/3's actual /order/create + approval_token
        # verification, not a re-implementation.
        try:
            order_resp = requests.post(
                f"{BACKEND_BASE_URL}/order/create",
                json={
                    "product_id": session["product_id"],
                    "quantity": quantity,
                    "approval_token": approval_token,
                },
                timeout=30,
            )
            order_resp.raise_for_status()
            order_body = order_resp.json()
            result.razorpay_order_id = order_body.get("razorpay_order_id")
        except requests.RequestException as e:
            # The negotiation itself succeeded; checkout completion failing
            # is worth recording but doesn't change the negotiation outcome.
            result.error = f"order/create failed after handoff: {e}"

    return result


def run_simulation(n: int, hesitation_rate: float, seed: int, regenerate: bool) -> dict:
    scenarios = load_or_generate_scenarios(n, hesitation_rate, seed, regenerate)

    try:
        catalog = _fetch_live_catalog()
    except requests.RequestException as e:
        raise SystemExit(
            f"Could not reach backend catalog at {BACKEND_BASE_URL}/catalog ({e}). "
            "This script requires a running backend — see README.md."
        )

    results: list[SessionResult] = []
    hesitating_count = 0
    processed = 0

    for scenario in scenarios:
        product = catalog.get(scenario["product_id"])
        if product is None:
            print(f"[skip] {scenario['session_id']}: product_id {scenario['product_id']} not in live catalog")
            continue

        unit_price = product["price"]
        quantity = scenario["quantity"]

        if not scenario["would_hesitate"]:
            results.append(
                SessionResult(
                    session_id=scenario["session_id"],
                    product_id=scenario["product_id"],
                    quantity=quantity,
                    would_hesitate=False,
                    shopper_persona=None,
                    original_unit_price=unit_price,
                    original_total_price=unit_price * quantity,
                    converted=True,
                    final_price=unit_price * quantity,
                )
            )
            processed += 1
            continue

        hesitating_count += 1
        processed += 1
        print(
            f"[{processed}/{len(scenarios)}] {scenario['session_id']} "
            f"(product={scenario['product_id']}, qty={quantity}, persona={scenario['shopper_persona']})..."
        )
        result = run_hesitating_session(scenario, unit_price)
        results.append(result)
        status = "CONVERTED" if result.converted else ("ERROR" if result.error else "LOST")
        print(f"    -> {status}" + (f" @ {result.final_price} paise" if result.final_price else "") + (f" ({result.error})" if result.error else ""))
        time.sleep(0.2)  # light pacing, avoid hammering the LLM provider

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend_base_url": BACKEND_BASE_URL,
        "session_count_requested": n,
        "session_count_processed": processed,
        "hesitation_rate_target": hesitation_rate,
        "seed": seed,
        "results": [asdict(r) for r in results],
    }


def aggregate(run_data: dict) -> dict:
    results = run_data["results"]
    hesitating = [r for r in results if r["would_hesitate"]]
    non_hesitating = [r for r in results if not r["would_hesitate"]]
    converted_hesitating = [r for r in hesitating if r["converted"]]
    errored = [r for r in hesitating if r.get("error")]

    baseline_total = sum(r["original_total_price"] for r in non_hesitating)  # hesitating baseline = 0
    with_agent_hesitating_total = sum(r["final_price"] or 0 for r in converted_hesitating)
    with_agent_total = sum(r["original_total_price"] for r in non_hesitating) + with_agent_hesitating_total

    gross_recovered_revenue = sum(r["original_total_price"] for r in converted_hesitating)
    discount_cost = sum(r["discount_given"] for r in converted_hesitating)
    net_recovered_revenue = gross_recovered_revenue - discount_cost  # == with_agent_hesitating_total

    recovery_rate = (len(converted_hesitating) / len(hesitating)) if hesitating else 0.0
    avg_discount = (discount_cost / len(converted_hesitating)) if converted_hesitating else 0.0

    persona_breakdown = {}
    for r in hesitating:
        p = r["shopper_persona"] or "unknown"
        bucket = persona_breakdown.setdefault(p, {"count": 0, "converted": 0})
        bucket["count"] += 1
        if r["converted"]:
            bucket["converted"] += 1

    return {
        "total_sessions": len(results),
        "hesitating_sessions": len(hesitating),
        "non_hesitating_sessions": len(non_hesitating),
        "converted_hesitating_sessions": len(converted_hesitating),
        "errored_hesitating_sessions": len(errored),
        "baseline_total_revenue_paise": baseline_total,
        "with_agent_total_revenue_paise": with_agent_total,
        "gross_recovered_revenue_paise": gross_recovered_revenue,
        "discount_cost_paise": discount_cost,
        "net_recovered_revenue_paise": net_recovered_revenue,
        "recovery_rate": recovery_rate,
        "avg_discount_per_recovered_session_paise": avg_discount,
        "persona_breakdown": persona_breakdown,
    }


def rupees(paise: float) -> str:
    return f"₹{paise / 100:,.2f}"


def write_report(run_data: dict, agg: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)

    persona_rows = "\n".join(
        f"| {persona} | {stats['count']} | {stats['converted']} | "
        f"{(stats['converted'] / stats['count'] * 100) if stats['count'] else 0:.0f}% |"
        for persona, stats in sorted(agg["persona_breakdown"].items())
    )

    report = f"""# Revenue Impact Simulation Report

**Generated:** {run_data['generated_at']}
**Backend:** {run_data['backend_base_url']} (real running instance — Phase 2/3's actual negotiation and policy-gate code, called over HTTP, not mocked)
**Random seed:** {run_data['seed']} (reproducible — re-running with the same seed and scenarios.json produces the same session assignments)

## What this number does and does not prove

**This simulation proves:** the real negotiation pipeline (seller agent + policy gate), when driven by a defined, scripted distribution of shopper reply patterns, converts a measurable share of hesitating sessions at a known, honestly-netted cost. Every negotiation call in this report is real — the same `/negotiate/start`, `/negotiate/message`, and `/order/create` endpoints a real user or the Phase 4b buyer agent would call.

**This simulation does NOT prove:** that real human shoppers actually behave like these scripted reply patterns, or that the assumed 35% hesitation rate reflects this (or any) real merchant's actual traffic. No real user behavior data informs either the hesitation rate or the reply scripts — both are stated assumptions, not measurements. Treat every dollar figure below as "what the pipeline would produce under these assumptions," not as a forecast.

## Assumptions (stated plainly — see README.md for the full list)

- **Sample size:** {run_data['session_count_processed']} synthetic sessions (target {run_data['session_count_requested']}), spread across the live seeded catalog.
- **Hesitation rate:** {run_data['hesitation_rate_target'] * 100:.0f}% of sessions are marked `would_hesitate: true`. {HESITATION_RATE_JUSTIFICATION}
- **Cart values:** synthetic — quantities randomly assigned (skewed toward 1 unit) against real catalog prices, not real order history.
- **Shopper replies:** scripted, not LLM-generated and not real user input — six fixed personas (immediate accept, counter-once-then-accept, counter-twice-then-accept, immediate reject, counter-then-reject, push-until-attempt-cap), randomly assigned to hesitating sessions.
- **Non-hesitating sessions** ({agg['non_hesitating_sessions']} of {agg['total_sessions']}) convert at full price under both conditions by construction — they are included in total revenue for completeness but contribute **zero** to the recovered-revenue figures below. All of the agent's measured value-add lives entirely inside the {agg['hesitating_sessions']}-session hesitating subset.

## Headline numbers

| Metric | Value |
|---|---|
| Total sessions simulated | {agg['total_sessions']} |
| Hesitating sessions | {agg['hesitating_sessions']} ({agg['hesitating_sessions'] / agg['total_sessions'] * 100:.0f}% of total) |
| Hesitating sessions converted (recovered) | {agg['converted_hesitating_sessions']} |
| **Recovery rate** (of hesitating sessions) | **{agg['recovery_rate'] * 100:.1f}%** |
| Hesitating sessions lost even with agent | {agg['hesitating_sessions'] - agg['converted_hesitating_sessions'] - agg['errored_hesitating_sessions']} |
| Sessions that errored (API/infra failure, not a negotiation rejection) | {agg['errored_hesitating_sessions']} |

## Revenue — gross, discount cost, and net (the honest number)

| Metric | Amount |
|---|---|
| Gross recovered revenue (full list price of every converted hesitating session — "value saved from being a total loss") | {rupees(agg['gross_recovered_revenue_paise'])} |
| **Total discount cost given** (what the gate approved away from list price) | **{rupees(agg['discount_cost_paise'])}** |
| **Net recovered revenue** (gross − discount cost = actual cash collected) | **{rupees(agg['net_recovered_revenue_paise'])}** |
| Average discount per recovered session | {rupees(agg['avg_discount_per_recovered_session_paise'])} |

Net recovered revenue is reported with equal weight to the gross figure, directly above it, on purpose — the gross number alone overstates the win by exactly the discount cost.

For context only (not the headline claim): baseline total revenue across all {agg['total_sessions']} sessions was {rupees(agg['baseline_total_revenue_paise'])}; with-agent total was {rupees(agg['with_agent_total_revenue_paise'])}. The difference between these two totals equals net recovered revenue above, since non-hesitating sessions are identical in both conditions by construction.

## Outcome by shopper persona

| Persona | Sessions | Converted | Conversion rate |
|---|---|---|---|
{persona_rows}

The `push_until_cap` persona exists specifically to exercise the policy gate's rejection and attempt-cap paths — a low conversion rate for that persona is expected and correct, not a bug.

## Reproducing this report

```bash
cd analysis
python simulate_revenue_impact.py               # reuses scenarios.json if present
python simulate_revenue_impact.py --regenerate-scenarios --seed 42
```

Raw per-session results (full conversation transcripts, negotiation session ids, order ids) are in `results/raw_results.json` for anyone who wants to audit an individual session's outcome rather than trust the aggregate.
"""

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)


def main():
    # Windows terminals often default stdout to a codepage (e.g. cp1252)
    # that can't encode the rupee sign this script prints — reconfigure to
    # UTF-8 rather than let a display-only issue crash after the real work
    # (and the report file) is already done.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Revenue impact simulation (Phase 5)")
    parser.add_argument("--n", type=int, default=DEFAULT_SESSION_COUNT)
    parser.add_argument("--hesitation-rate", type=float, default=DEFAULT_HESITATION_RATE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--regenerate-scenarios", action="store_true")
    args = parser.parse_args()

    run_data = run_simulation(args.n, args.hesitation_rate, args.seed, args.regenerate_scenarios)
    agg = aggregate(run_data)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(RAW_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"run": run_data, "aggregate": agg}, f, indent=2)

    write_report(run_data, agg)

    print("\n=== SUMMARY ===")
    print(f"Total sessions: {agg['total_sessions']}, hesitating: {agg['hesitating_sessions']}")
    print(f"Recovery rate: {agg['recovery_rate'] * 100:.1f}%")
    print(f"Gross recovered: {rupees(agg['gross_recovered_revenue_paise'])}")
    print(f"Discount cost: {rupees(agg['discount_cost_paise'])}")
    print(f"NET recovered: {rupees(agg['net_recovered_revenue_paise'])}")
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
