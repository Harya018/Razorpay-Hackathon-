# Revenue Impact Simulation Report

**Generated:** 2026-08-24T11:20:22.211968+00:00
**Backend:** http://localhost:8010 (real running instance — Phase 2/3's actual negotiation and policy-gate code, called over HTTP, not mocked)
**Random seed:** 42 (reproducible — re-running with the same seed and scenarios.json produces the same session assignments)

## What this number does and does not prove

**This simulation proves:** the real negotiation pipeline (seller agent + policy gate), when driven by a defined, scripted distribution of shopper reply patterns, converts a measurable share of hesitating sessions at a known, honestly-netted cost. Every negotiation call in this report is real — the same `/negotiate/start`, `/negotiate/message`, and `/order/create` endpoints a real user or the Phase 4b buyer agent would call.

**This simulation does NOT prove:** that real human shoppers actually behave like these scripted reply patterns, or that the assumed 35% hesitation rate reflects this (or any) real merchant's actual traffic. No real user behavior data informs either the hesitation rate or the reply scripts — both are stated assumptions, not measurements. Treat every dollar figure below as "what the pipeline would produce under these assumptions," not as a forecast.

## Assumptions (stated plainly — see README.md for the full list)

- **Sample size:** 60 synthetic sessions (target 60), spread across the live seeded catalog.
- **Hesitation rate:** 35% of sessions are marked `would_hesitate: true`. Published e-commerce cart-abandonment studies (e.g. Baymard Institute meta-analyses) commonly cite AVERAGE abandonment in the 60-80% range across all causes (shipping cost surprises, forced account creation, just browsing, etc.) — most of that is NOT price-sensitive and would not respond to a negotiation-style intervention. This simulation assumes a deliberately more conservative 35% of sessions represent genuine, price-related hesitation that a negotiation offer could plausibly address. This is a reasonable, stated assumption for demonstration purposes — it is NOT a measured figure for this specific merchant, and no real user behavior data informs it.
- **Cart values:** synthetic — quantities randomly assigned (skewed toward 1 unit) against real catalog prices, not real order history.
- **Shopper replies:** scripted, not LLM-generated and not real user input — six fixed personas (immediate accept, counter-once-then-accept, counter-twice-then-accept, immediate reject, counter-then-reject, push-until-attempt-cap), randomly assigned to hesitating sessions.
- **Non-hesitating sessions** (32 of 60) convert at full price under both conditions by construction — they are included in total revenue for completeness but contribute **zero** to the recovered-revenue figures below. All of the agent's measured value-add lives entirely inside the 28-session hesitating subset.

## Headline numbers

| Metric | Value |
|---|---|
| Total sessions simulated | 60 |
| Hesitating sessions | 28 (47% of total) |
| Hesitating sessions converted (recovered) | 11 |
| **Recovery rate** (of hesitating sessions) | **39.3%** |
| Hesitating sessions lost even with agent | 16 |
| Sessions that errored (API/infra failure, not a negotiation rejection) | 1 |

## Revenue — gross, discount cost, and net (the honest number)

| Metric | Amount |
|---|---|
| Gross recovered revenue (full list price of every converted hesitating session — "value saved from being a total loss") | ₹29,881.00 |
| **Total discount cost given** (what the gate approved away from list price) | **₹2,524.70** |
| **Net recovered revenue** (gross − discount cost = actual cash collected) | **₹27,356.30** |
| Average discount per recovered session | ₹229.52 |

Net recovered revenue is reported with equal weight to the gross figure, directly above it, on purpose — the gross number alone overstates the win by exactly the discount cost.

For context only (not the headline claim): baseline total revenue across all 60 sessions was ₹107,542.00; with-agent total was ₹134,898.30. The difference between these two totals equals net recovered revenue above, since non-hesitating sessions are identical in both conditions by construction.

## Outcome by shopper persona

| Persona | Sessions | Converted | Conversion rate |
|---|---|---|---|
| counter_once_then_accept | 6 | 6 | 100% |
| counter_then_reject | 6 | 0 | 0% |
| counter_twice_then_accept | 5 | 1 | 20% |
| immediate_accept | 4 | 4 | 100% |
| immediate_reject | 4 | 0 | 0% |
| push_until_cap | 3 | 0 | 0% |

The `push_until_cap` persona exists specifically to exercise the policy gate's rejection and attempt-cap paths — a low conversion rate for that persona is expected and correct, not a bug.

## Reproducing this report

```bash
cd analysis
python simulate_revenue_impact.py               # reuses scenarios.json if present
python simulate_revenue_impact.py --regenerate-scenarios --seed 42
```

Raw per-session results (full conversation transcripts, negotiation session ids, order ids) are in `results/raw_results.json` for anyone who wants to audit an individual session's outcome rather than trust the aggregate.
