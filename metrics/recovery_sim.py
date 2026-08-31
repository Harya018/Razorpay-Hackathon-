"""Revenue-recovery measurement harness — Phase 13.

Runs N simulated abandoned-cart sessions through the REAL storefront
negotiation flow (POST /negotiate/start, POST /negotiate/message) end to
end. Nothing about the negotiation logic, the discount ladder, or the
policy gate is mocked — every session is a genuine HTTP round trip through
the same backend/policy-gate the real storefront uses, own venv, HTTP-only,
no imports from backend source (same independence discipline as
buyer-agent/redteam/red-team-agent).

The ONE thing that IS simulated, and is stated as such throughout this
file's output: whether a shopper accepts a given offer. There is no real
customer in this harness — see MODEL DOCUMENTATION below for exactly what
distribution decides that, and why. Every OTHER number in the results
(what discount was actually offered at which attempt, whether the policy
gate approved it, the real approval_token/checkout_amount) comes straight
from the real negotiation graph and policy gate, not from this harness's
own arithmetic.

=== MODEL DOCUMENTATION (the honesty-boundary statement this phase asked for) ===

Each simulated shopper draws ONE number, `required_discount_pct`, from
Uniform(0, 20) — "the smallest discount this shopper would have accepted."
A shopper accepts the FIRST offer whose real discount percentage (computed
from the actual proposed_offer.value the server returns, never
reassumed) meets or exceeds that number. The real discount ladder here
only ever offers two distinct percentages (5% then 10% — see
backend/app/agent/discount_ladder.py's DEFAULT_LADDER, read as public
config, not imported) with a 3rd "this is final" framing of the same 10%
— so Uniform(0, 20) means: ~25% of simulated shoppers are satisfied by
5%, ~25% more are satisfied by 10%, and the remaining ~50% would need
MORE than this merchant's ceiling ever offers and should never convert on
price alone.

On top of that pure price threshold, the FINAL rung (attempt 3, "this is
truly our best price") gets one small, separately-documented boost: a
flat URGENCY_BOOST=15% chance of the shopper converting anyway, purely
from the closing-offer framing, independent of their price threshold —
modeling ordinary urgency/last-chance behavior, not a price effect. This
is the only place anything other than the stated price-threshold model
decides an outcome, and it is applied nowhere else.

This is a controlled estimate of what the ladder mechanism COULD recover
under an assumed, disclosed shopper-behavior distribution — it is NOT a
claim about real shopper conversion rates, which this project has no data
on. Changing the Uniform(0, 20) bound, or removing the urgency boost,
would materially change every headline number below; that sensitivity is
the point of stating the model explicitly rather than only reporting a
final percentage.
"""

import argparse
import asyncio
import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8010"
REQUIRED_DISCOUNT_MAX_PCT = 20.0  # Uniform(0, this) — see module docstring
URGENCY_BOOST_PROB = 0.15  # flat extra acceptance chance at the final rung only
MAX_ATTEMPTS = 3  # matches backend/app/agent/nodes.py's MAX_OFFER_ATTEMPTS
THINKING_TIME_RANGE_SECONDS = (15, 120)  # simulated per-turn shopper response time — NOT real wall-clock API latency


@dataclass
class SessionResult:
    session_id: Optional[str]
    product_id: int
    product_name: str
    quantity: int
    original_cart_value_paise: int
    required_discount_pct: float  # this simulated shopper's own threshold — recorded for auditability
    popup_triggered: bool
    converted: bool
    closing_tier: Optional[int]  # attempt_number that closed the sale, or None
    closing_discount_pct: Optional[float]
    final_discount_paise: Optional[int]  # original - final, i.e. money actually given up
    simulated_time_to_outcome_seconds: float
    error: Optional[str] = None


async def _fetch_catalog(client: httpx.AsyncClient, base_url: str) -> list[dict]:
    resp = await client.get(f"{base_url}/catalog")
    resp.raise_for_status()
    return [p for p in resp.json() if p.get("stock", 0) > 0]


def _discount_pct(original_total: int, offered_value: int) -> float:
    if original_total <= 0:
        return 0.0
    return (original_total - offered_value) / original_total * 100


async def _run_one_session(
    client: httpx.AsyncClient, base_url: str, product: dict, rng: random.Random
) -> SessionResult:
    quantity = rng.choice([1, 1, 2])  # weighted toward single-unit carts, still realistic variation
    original_total = product["price"] * quantity
    required_pct = rng.uniform(0, REQUIRED_DISCOUNT_MAX_PCT)
    thinking_times: list[float] = []

    result = SessionResult(
        session_id=None,
        product_id=product["id"],
        product_name=product["name"],
        quantity=quantity,
        original_cart_value_paise=original_total,
        required_discount_pct=round(required_pct, 2),
        popup_triggered=True,  # this harness always fires the negotiation trigger it's testing
        converted=False,
        closing_tier=None,
        closing_discount_pct=None,
        final_discount_paise=None,
        simulated_time_to_outcome_seconds=0.0,
    )

    try:
        start_resp = await client.post(
            f"{base_url}/negotiate/start",
            json={"product_id": product["id"], "cart_quantity": quantity},
            timeout=90,
        )
        start_resp.raise_for_status()
        body = start_resp.json()
        result.session_id = body["session_id"]

        for attempt in range(1, MAX_ATTEMPTS + 1):
            thinking_times.append(rng.uniform(*THINKING_TIME_RANGE_SECONDS))

            # The graph can close on its OWN judgment (decide_to_offer's
            # "only offer again if it has a real chance" logic, or the
            # attempt cap) without producing a fresh offer this turn — in
            # that case proposed_offer still echoes the LAST real offer
            # from a previous turn, not a fresh one for THIS attempt.
            # Checking closed first, before ever looking at proposed_offer,
            # is what prevents this harness from re-evaluating (and
            # possibly "accepting", or sending a message into) a session
            # that has already ended server-side.
            if body.get("closed"):
                break

            offer = body.get("proposed_offer")
            if not offer or offer.get("value") is None:
                break  # no offer on this turn (e.g. gate rejected everything) — nothing to evaluate

            offered_pct = _discount_pct(original_total, offer["value"])
            is_final_rung = attempt >= MAX_ATTEMPTS
            accepts_on_price = offered_pct >= required_pct - 1e-9
            accepts_on_urgency = is_final_rung and rng.random() < URGENCY_BOOST_PROB
            accepted = accepts_on_price or accepts_on_urgency

            if accepted:
                accept_resp = await client.post(
                    f"{base_url}/negotiate/message",
                    json={"session_id": result.session_id, "user_message": "That works, I'll take it — let's proceed."},
                    timeout=90,
                )
                accept_resp.raise_for_status()
                accept_body = accept_resp.json()
                result.converted = accept_body.get("offer_status") == "accepted" and bool(accept_body.get("handoff"))
                if result.converted:
                    result.closing_tier = attempt
                    result.closing_discount_pct = round(offered_pct, 2)
                    final_value = accept_body.get("checkout_amount") or offer["value"]
                    result.final_discount_paise = original_total - final_value
                break

            if is_final_rung:
                decline_resp = await client.post(
                    f"{base_url}/negotiate/message",
                    json={"session_id": result.session_id, "user_message": "No thanks, not interested — I'll pass."},
                    timeout=90,
                )
                decline_resp.raise_for_status()
                break

            counter_resp = await client.post(
                f"{base_url}/negotiate/message",
                json={"session_id": result.session_id, "user_message": "That's still not quite enough for me — can you do any better?"},
                timeout=90,
            )
            counter_resp.raise_for_status()
            body = counter_resp.json()

    except httpx.HTTPStatusError as e:
        result.error = f"{type(e).__name__}: HTTP {e.response.status_code} for {e.request.url} — body: {e.response.text}"
    except httpx.HTTPError as e:
        result.error = f"{type(e).__name__}: {e}"

    result.simulated_time_to_outcome_seconds = round(sum(thinking_times), 1)
    return result


async def run(n: int, base_url: str, seed: int, concurrency: int) -> list[SessionResult]:
    rng = random.Random(seed)
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        catalog = await _fetch_catalog(client, base_url)
        if not catalog:
            raise RuntimeError(f"No in-stock products returned from {base_url}/catalog — is the backend running and seeded?")

        # Pre-draw each session's product choice with the seeded RNG BEFORE
        # spawning concurrent tasks, so the sequence of draws (and therefore
        # the whole run) stays reproducible regardless of how the event
        # loop happens to interleave concurrent requests.
        chosen_products = [rng.choice(catalog) for _ in range(n)]
        session_rngs = [random.Random(rng.random()) for _ in range(n)]

        async def _bounded(i: int) -> SessionResult:
            async with semaphore:
                return await _run_one_session(client, base_url, chosen_products[i], session_rngs[i])

        return list(await asyncio.gather(*[_bounded(i) for i in range(n)]))


def _aggregate(results: list[SessionResult]) -> dict:
    total = len(results)
    errored = [r for r in results if r.error]
    usable = [r for r in results if not r.error]
    converted = [r for r in usable if r.converted]

    recovery_rate = len(converted) / len(usable) if usable else 0.0
    avg_discount_pct = (
        sum(r.closing_discount_pct for r in converted) / len(converted) if converted else None
    )
    avg_time_to_recovery = (
        sum(r.simulated_time_to_outcome_seconds for r in converted) / len(converted) if converted else None
    )
    avg_time_to_giveup = (
        sum(r.simulated_time_to_outcome_seconds for r in usable if not r.converted) / len([r for r in usable if not r.converted])
        if any(not r.converted for r in usable) else None
    )
    total_recovered_revenue = sum(
        (r.original_cart_value_paise - (r.final_discount_paise or 0)) for r in converted
    )
    total_discount_given = sum(r.final_discount_paise or 0 for r in converted)

    by_tier: dict[str, int] = {}
    for r in converted:
        label = {1: "5% (attempt 1)", 2: "10% (attempt 2)", 3: "10% final/urgency (attempt 3)"}.get(
            r.closing_tier, f"attempt {r.closing_tier}"
        )
        by_tier[label] = by_tier.get(label, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sessions_requested": total,
        "sessions_errored": len(errored),
        "sessions_usable": len(usable),
        "recovery_rate": round(recovery_rate, 4),
        "conversions": len(converted),
        "avg_discount_pct_among_conversions": round(avg_discount_pct, 2) if avg_discount_pct is not None else None,
        "avg_simulated_seconds_to_recovery": round(avg_time_to_recovery, 1) if avg_time_to_recovery is not None else None,
        "avg_simulated_seconds_to_giveup": round(avg_time_to_giveup, 1) if avg_time_to_giveup is not None else None,
        "total_recovered_revenue_paise": total_recovered_revenue,
        "total_discount_given_paise": total_discount_given,
        "closing_tier_breakdown": by_tier,
        "errors": [r.error for r in errored][:10],  # sample, not the full list, to keep this readable
    }


def _print_summary(agg: dict, n: int, seed: int, base_url: str) -> None:
    print("\n" + "=" * 70)
    print("REVENUE-RECOVERY SIMULATION — SUMMARY")
    print("=" * 70)
    print(
        f"\nHONESTY NOTE: customer acceptance is SIMULATED, not real shopper "
        f"data. Each simulated shopper's acceptance threshold is drawn from "
        f"Uniform(0, {REQUIRED_DISCOUNT_MAX_PCT:.0f}%), plus a flat "
        f"{URGENCY_BOOST_PROB:.0%} urgency-driven acceptance chance at the "
        f"final offer only. This is a controlled estimate of what the "
        f"discount-ladder MECHANISM could recover under that assumed "
        f"distribution — not a claim about real-world shopper behavior. "
        f"See this script's module docstring for the full model."
    )
    print(f"\nRan against: {base_url}  |  n={n}  |  seed={seed} (reproducible)")
    print(f"\nSessions: {agg['sessions_usable']}/{agg['sessions_requested']} completed cleanly"
          + (f" ({agg['sessions_errored']} errored)" if agg["sessions_errored"] else ""))

    pct = agg["recovery_rate"] * 100
    print(f"\n>>> TOP-LINE: recovered {pct:.0f}% of abandoned carts across {agg['sessions_usable']} simulated sessions <<<\n")

    print(f"Conversions: {agg['conversions']}")
    if agg["avg_discount_pct_among_conversions"] is not None:
        print(f"Average discount given (among conversions): {agg['avg_discount_pct_among_conversions']:.1f}%")
    print(f"Total revenue recovered (simulated): Rs {agg['total_recovered_revenue_paise'] / 100:,.2f}")
    print(f"Total discount given away (simulated): Rs {agg['total_discount_given_paise'] / 100:,.2f}")
    if agg["avg_simulated_seconds_to_recovery"] is not None:
        print(f"Average SIMULATED time-to-recovery: {agg['avg_simulated_seconds_to_recovery']:.0f}s (simulated shopper thinking time, not API latency)")
    if agg["avg_simulated_seconds_to_giveup"] is not None:
        print(f"Average SIMULATED time-to-giveup (non-converters): {agg['avg_simulated_seconds_to_giveup']:.0f}s")

    print("\nClosing tier breakdown (which rung actually closed the sale):")
    if agg["closing_tier_breakdown"]:
        for tier, count in sorted(agg["closing_tier_breakdown"].items()):
            print(f"  {tier}: {count} ({count / agg['conversions'] * 100:.0f}% of conversions)")
    else:
        print("  (no conversions this run)")

    if agg["sessions_errored"]:
        print(f"\n{agg['sessions_errored']} session(s) errored (network/backend issue, not a shopper decision) — sample:")
        for e in agg["errors"]:
            print(f"  - {e}")
    print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Revenue-recovery simulation against the real negotiation flow")
    parser.add_argument("--n", type=int, default=50, help="number of simulated abandoned-cart sessions (default 50)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed — same seed always reproduces the same run")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="backend base URL")
    parser.add_argument("--concurrency", type=int, default=5, help="max concurrent sessions in flight")
    parser.add_argument("--out", default="results/recovery_sim.json", help="output JSON path")
    args = parser.parse_args()

    t0 = time.time()
    results = asyncio.run(run(args.n, args.base_url, args.seed, args.concurrency))
    wall_seconds = round(time.time() - t0, 1)

    agg = _aggregate(results)
    agg["wall_clock_seconds_for_this_run"] = wall_seconds
    agg["rng_seed"] = args.seed
    agg["concurrency"] = args.concurrency
    agg["model_documentation"] = (
        f"Customer acceptance is SIMULATED. Each shopper draws required_discount_pct ~ "
        f"Uniform(0, {REQUIRED_DISCOUNT_MAX_PCT:.0f}) and accepts the first real offer whose actual "
        f"discount %% meets that threshold; the final rung additionally gets a flat "
        f"{URGENCY_BOOST_PROB:.0%} urgency-acceptance chance independent of price. Not a claim about "
        f"real shopper behavior — a controlled estimate of the ladder mechanism's ceiling under this "
        f"disclosed distribution."
    )

    out_path = Path(__file__).parent / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"summary": agg, "sessions": [asdict(r) for r in results]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _print_summary(agg, args.n, args.seed, args.base_url)
    print(f"Wrote full results to {out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
