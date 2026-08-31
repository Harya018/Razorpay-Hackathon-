# Revenue Impact Simulation (Phase 5)

A standalone script producing one defensible number for the "grows the
merchant's revenue" half of the track rubric — clearly labeled as a
simulation, not production telemetry.

**This does not modify, import from, or get imported by `/backend`,
`/policy-gate`, `/frontend`, or `/buyer-agent`.** It is a one-way HTTP
client against the backend's real running API — the exact same
`/negotiate/start`, `/negotiate/message`, and `/order/create` endpoints a
real shopper or the Phase 4b buyer agent would call. Nothing about the
seller agent's or policy gate's actual decision logic is reimplemented or
mocked here.

## What this measures, and what it doesn't

Read this before citing any number from `results/revenue_impact_report.md`
on a slide.

**Measures:** given a defined, scripted distribution of shopper reply
patterns hitting a defined hesitation-trigger rate, what does the REAL
negotiation pipeline (Phase 2's seller agent, Phase 3's policy gate,
actually running) produce — conversion rate, final price, discount cost?

**Does NOT measure:** whether real human shoppers behave anything like
the scripted reply patterns used here, or whether a negotiation offer at
any tested rate actually changes real purchase behavior. That is a
conversion-psychology question. This script has no data on it and makes
no claim about it — every dollar figure this script produces is
conditional on "if sessions hesitate and reply the way these scripts do,"
not "here is what will actually happen with real traffic."

## Assumptions — stated plainly

- **Sample size:** 60 synthetic sessions by default (`--n`), spread
  across the live seeded catalog, fetched from the running backend at
  generation time (never hardcoded prices).
- **Hesitation rate:** 35% by default (`--hesitation-rate`). Published
  e-commerce cart-abandonment studies (e.g. Baymard Institute
  meta-analyses) commonly cite *average* abandonment in the 60-80% range
  across all causes — most of which is unrelated to price (shipping cost
  surprises, forced account creation, just browsing, etc.) and would not
  respond to a negotiation-style intervention. 35% is a deliberately more
  conservative, stated assumption for the subset of sessions that
  represent genuine, price-related hesitation a negotiation offer could
  plausibly address. **This is not a measured figure for this or any
  real merchant.**
- **Cart values:** synthetic quantities (1-3 units, skewed toward 1),
  randomly assigned per session against real catalog prices — not real
  order history, because none exists for this project.
- **Shopper replies:** six fixed, scripted reply patterns (see
  `PERSONA_SCRIPTS` in `simulate_revenue_impact.py`), randomly assigned to
  hesitating sessions:
  - `immediate_accept` — accepts the opening offer
  - `counter_once_then_accept` — counters once, then accepts
  - `counter_twice_then_accept` — counters twice, then accepts
  - `immediate_reject` — rejects the opening offer outright
  - `counter_then_reject` — counters once, then walks away
  - `push_until_cap` — repeatedly pushes for an unreasonable discount,
    exercising the policy gate's rejection and attempt-cap paths; expected
    to convert rarely or never
  These are fixed strings, not LLM-generated and not real user input.
  Reproducible by design — the same seed produces the same persona
  assignment every run.
- **Non-hesitating sessions** convert at full listed price under both
  the baseline and with-agent condition by construction (nothing about
  them changes). They're included in total revenue for completeness but
  contribute nothing to the recovered-revenue figures — inflating the
  headline number by mixing them in would be misleading, so the report
  doesn't do that.

## Reproducing

Requires the backend running (`http://localhost:8010` by default,
override with `BACKEND_BASE_URL`) with at least one seeded product.

```bash
cd analysis
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python simulate_revenue_impact.py                                  # reuses scenarios.json if present
python simulate_revenue_impact.py --regenerate-scenarios --seed 42 # regenerate with a fixed seed
python simulate_revenue_impact.py --n 100 --hesitation-rate 0.4    # different sample size / rate
```

Each hesitating session makes real HTTP calls (and real Groq LLM calls,
via the backend's seller agent) — expect roughly 3-8 seconds per
negotiation turn, so a 60-session run at the default 35% hesitation rate
(≈21 hesitating sessions, 1-3 turns each) takes several minutes. This is
deliberate: the whole point is that nothing here is mocked.

## Outputs

- `scenarios.json` — the generated (or reused) synthetic session
  definitions: `session_id`, `product_id`, `quantity`, `would_hesitate`,
  `shopper_persona`.
- `results/revenue_impact_report.md` — the report: sample size,
  hesitation rate and justification, recovery rate, gross recovered
  revenue, discount cost, net recovered revenue, and the same
  what-this-does-and-doesn't-prove statement repeated here.
- `results/raw_results.json` — full per-session detail, including the
  entire scripted conversation transcript and real `negotiation_session_id`
  / `razorpay_order_id` for every converted session, for anyone who wants
  to audit one session's outcome rather than trust the aggregate.

## Keeping this separate from production telemetry

Every file this script produces lives under `/analysis`, is named
`*simulation*` / `*sim-*`, and every session_id it generates is prefixed
`sim-` specifically so it's never mistaken for a real negotiation session
in the backend's audit log if someone greps for it later.
