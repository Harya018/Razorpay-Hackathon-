# Bounded Agentic Checkout

A Razorpay-backed checkout system where both human shoppers and
autonomous AI buyer agents can negotiate discounts and pay — with every
money-affecting decision made by a separate, deterministic **Policy
Gate** that no LLM can override. "Priya's Shop" (handmade home decor) is
the storefront persona; the Merchant Dashboard and Sales Analytics pages
are where the architecture itself — bounded, gated, audited — is made
visible.

This README covers getting all **four services** running from a clean
checkout. If you hit something not covered here, that's a real gap —
see "Known Gotchas" below, and please add to it.

## Architecture at a glance

| Service | Port | What it is |
|---|---|---|
| `backend` | **8010** | FastAPI. Catalog, orders, human negotiation (LangGraph seller agent), the agent-commerce API (`/agent/v1/*`), the Merchant Dashboard's read endpoints, hash-chained audit log. |
| `policy-gate` | **8001** | Separate FastAPI process, **separate SQLite DB**, own venv. The sole authority on whether a discount is approved — deterministic, zero LLM calls, HTTP-only coupling to `backend`. |
| `buyer-agent` | **8020** | Separate FastAPI process, own venv, zero code imports from `backend`. A LangGraph shopping agent that negotiates and buys via `backend`'s public `/agent/v1/*` API only. Also runnable as a one-shot CLI (see below). |
| `frontend` | **5173** | React + Vite. The storefront ("Priya's Shop"), cart, Merchant Dashboard, and Sales Analytics. |

`backend` is the hub — `policy-gate`, `buyer-agent`, and `frontend` all
talk to it, never to each other directly.

## Prerequisites

- Python 3.11+
- Node.js 18+
- A [Razorpay](https://razorpay.com) account with **Test Mode** enabled
- A [Groq](https://console.groq.com) API key (free tier works) — powers
  the seller negotiation agent and, separately, the buyer agent
- Optional: a [Gemini](https://aistudio.google.com/apikey) API key, used
  only as a fallback tier if Groq is rate-limited

## Get Razorpay test keys

1. Log into the Razorpay Dashboard and switch to **Test Mode** (toggle top-left).
2. **Settings → API Keys → Generate Test Key** — copy the Key ID (`rzp_test_...`) and Key Secret.
3. **Settings → Webhooks → Add New Webhook** (only needed if you want live payment-status updates; the demo works without it):
   - URL: `http://<your-public-tunnel>/webhook/razorpay` (use `ngrok http 8010` or similar — Razorpay needs to reach your local backend)
   - Active events: `payment.captured`, `payment.failed`
   - Copy the generated **Webhook Secret**

## 1. Backend setup (port 8010)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
copy .env.example .env        # Windows: copy, macOS/Linux: cp
```

Edit `backend/.env` and fill in `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`
(test-mode values from above) and `GROQ_API_KEY`. `RAZORPAY_WEBHOOK_SECRET`
and everything else can stay blank/default for a local demo.

Run it:

```bash
uvicorn app.main:app --reload --port 8010
```

Tables are created automatically on startup (SQLite, `backend/app.db`).

**Seed the catalog — required, not optional.** The storefront shows
nothing at all until you do this:

```bash
python scripts/seed_catalog.py
```

This creates Priya's Shop's 12 handmade-decor products. Safe to re-run
any time (idempotent, matched by product name).

## 2. Policy-gate setup (port 8001)

Separate virtual environment, separate process, separate database — this
is deliberate (see `docs/` for the architecture rationale). It's the
only service allowed to approve a discount.

```bash
cd policy-gate
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

`GATE_SECRET` in `.env` should be a real random value (`openssl rand -hex 32`) —
the placeholder is fine for local dev, just never commit a real one.

```bash
uvicorn app.main:app --reload --port 8001
```

Verify: `curl http://127.0.0.1:8001/health` → `{"status": "ok", "uptime_seconds": ...}`

## 3. Buyer-agent setup (port 8020) — optional, needed for AI-agent demos only

A fully independent service (own venv, zero imports from `backend`) that
shops against `backend`'s public agent-commerce API. Skip this if you
only care about the human shopper flow.

```bash
cd buyer-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

You need a buyer identity first (`backend` must already be running):

```bash
curl -X POST http://127.0.0.1:8010/agent/v1/register ^
  -H "Content-Type: application/json" ^
  -d "{\"buyer_agent_id\": \"your-bot-name\", \"display_name\": \"Your Bot\"}"
```

Copy the returned `api_key` into `.env` as `BUYER_API_KEY`, and your
chosen `buyer_agent_id` as `BUYER_AGENT_ID`. Set `GROQ_API_KEY` too — a
separate key from the backend's, even if it's the same provider.

**Two ways to run it:**

- **One-shot CLI** (autonomous, no human in the loop):
  ```bash
  python -m app.main "a warm-toned ceramic vase under 2500 rupees"
  python -m app.main "a stoneware mug" --aggressive   # forces an unreasonable ask, tests the policy gate's ceiling
  ```
- **Interactive HTTP server** (what powers a real back-and-forth with a
  person approving each step — `POST /shopper/start` then
  `POST /shopper/chat`):
  ```bash
  uvicorn app.server:app --reload --port 8020
  ```

See `buyer-agent/README.md` for the full interface.

## 4. Frontend setup (port 5173)

```bash
cd frontend
npm install
copy .env.local.example .env.local
npm run dev
```

Opens on `http://localhost:5173`. Nav: **Shop** (storefront) / **Catalog
(admin)** / **Merchant Dashboard** / **Sales Analytics** / **Cart**.

## Startup order

`backend` first (everything else depends on it) → `policy-gate` and
`buyer-agent` in either order → `frontend` last. None of the four crash
if a dependency isn't up yet, but real functionality (negotiation,
checkout) needs `backend` + `policy-gate` at minimum.

## Known Gotchas

### "localhost" vs "127.0.0.1" — a real, measured performance bug

On this project's dev machine (Windows), resolving the hostname
**`localhost`** tries IPv6 (`::1`) first, times out, then falls back to
IPv4 — adding real, reproducible latency to *every single request*:

| Client | `localhost` | `127.0.0.1` |
|---|---|---|
| Python `requests` (backend → policy-gate, buyer-agent → backend) | ~2.08s | ~0.016s |
| Browser `fetch()` (frontend → backend) | ~357ms | ~24ms |

This is not hypothetical — it was found live, twice, in two different
places in this codebase (`backend/app/config.py`'s `POLICY_GATE_URL`,
and `buyer-agent/app/config.py`'s `SELLER_BASE_URL`), each time because a
config default said `localhost` instead of `127.0.0.1`. Every real
negotiation and every buyer-agent purchase was silently eating this tax
until it was fixed. **Every `.env.example` in this repo now defaults to
`127.0.0.1`** — if you ever add a new inter-service URL, use `127.0.0.1`,
not `localhost`, or re-measure before assuming it doesn't matter.

(One asymmetry worth knowing: `vite`, the frontend dev server itself,
binds to `[::1]` by default, not `127.0.0.1` — so *reaching the frontend
dev server* should use `http://localhost:5173`, even though everything
the frontend *calls out to* should use `127.0.0.1`.)

### The catalog is empty until you run `seed_catalog.py`

Not a bug, but easy to miss — `backend`'s tables are created automatically,
but nothing populates them until you explicitly run
`python scripts/seed_catalog.py` (see step 1 above). The storefront loads
fine with zero products; it just looks broken if you don't know why.

### Port 8010, not 8000

Earlier phases of this project ran the backend on port 8000; every
service now uses **8010**. If you find a stray reference to `:8000`
anywhere (a script, a comment, an old note), it's stale — file it as a
doc bug.

### `POLICY_GATE_TEST_HOOKS`

`policy-gate` has one env var, `POLICY_GATE_TEST_HOOKS=1`, that enables
adversarial-testing-only delay hooks in `/evaluate` (see
`tests/phase17_trust_boundary/`). It's a no-op for any real request
(gated behind a magic `session_id` prefix no real caller would ever
send) but **should never be set during a demo** — it's for that test
suite only, and the test suite itself always restores a normal instance
when it finishes.

## Manual end-to-end test — human shopper

With all four services up and the catalog seeded:

1. Open `http://localhost:5173/shop` — confirm Priya's Shop's 12 products appear.
2. Click into a product, **Add to Cart**, then leave the cart alone.
3. Wait past `VITE_CART_ABANDONMENT_THRESHOLD_SECONDS` (60s by default;
   lower it in `.env.local` for a faster local test) — a negotiation
   popup ("a note from Priya") appears **automatically**. There is no
   manual "Start Negotiation" button anymore (removed — see
   `WHAT_BROKE.md`); this auto-trigger *is* the intended flow.
4. Accept the offer or keep negotiating in the popup.
5. Proceed to checkout — pay with a
   [Razorpay test card](https://razorpay.com/docs/payments/payments/test-card-upi-details/)
   (`4111 1111 1111 1111`, any future expiry, any CVV).
6. Check `http://localhost:5173/dashboard` — the order, the negotiation,
   and the hash-chained audit trail entries for it should all be visible
   live.

## Manual end-to-end test — AI buyer agent

With `backend`, `policy-gate`, and `buyer-agent` up (frontend optional
for this one — watch it happen on the Merchant Dashboard's "AI Buyer
Agents" tab instead):

```bash
cd buyer-agent
python -m app.main "a hand-painted ceramic vase, negotiate if you can"
```

Watch `http://localhost:5173/dashboard/agent-conversations` for the
live exchange (Seller Agent and Buyer Agent both LLM-driven and shown in
dashed violet; Policy Gate shown in solid slate — see the architecture
diagram in `docs/` for why).

## Where everything else lives

- `docs/` — architecture diagram, the agent-commerce interface contract, x402 conformance notes.
- `redteam/` and `red-team-agent/` — two independent adversarial test suites, run against the live system (see the Merchant Dashboard's "Security Posture" panel for the latest results).
- `tests/phase17_trust_boundary/` — six adversarial pytest suites proving (or disproving) specific trust-boundary claims against the live services; `results.md` in that directory has the latest run.
- `metrics/recovery_sim.py` — the revenue-recovery *simulation* behind the dashboard's "Revenue Recovery (Simulated)" card. See the methodology note next to that card in the Sales Analytics page for exactly what it does and doesn't claim.
- `demo/` — scripted failure-mode demo beats (e.g. killing `policy-gate` mid-negotiation to show fail-closed behavior live).
- `WHAT_BROKE.md` — a plain, non-defensive account of every real bug found across this build, including via live red-teaming and adversarial testing. Read it if you want to know what's actually been checked, not just claimed.
- `RUBRIC_MAPPING.md` — how this project maps to the actual judging criteria.
