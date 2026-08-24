# Bounded Agentic Checkout — Phase 1: Foundation

Phase 1 scope only: project structure, database schema, core catalog CRUD, and
a real Razorpay test-mode payment flow. No agent logic, no negotiation, no
policy-gate decision logic — see [`main.py`](policy-gate/app/main.py) in
`policy-gate` for why that service exists but does nothing yet.

This phase runs **three independent processes**:

| Process | Port | Purpose |
|---|---|---|
| `backend` | 8000 | Seller-side API: catalog, orders, Razorpay webhook |
| `policy-gate` | 8001 | Stub service — only `/health`. Proves the service boundary is real from day one; Phase 3 adds decision logic here, called over HTTP, never in-process from `backend` |
| `frontend` | 5173 | React catalog UI + Razorpay hosted checkout |

## Prerequisites

- Python 3.11+
- Node.js 18+
- A [Razorpay](https://razorpay.com) account with **Test Mode** enabled

## Get Razorpay test keys

1. Log into the Razorpay Dashboard and switch to **Test Mode** (toggle top-left).
2. Go to **Settings → API Keys → Generate Test Key** — copy the Key ID (`rzp_test_...`) and Key Secret.
3. Go to **Settings → Webhooks → Add New Webhook**:
   - URL: `http://<your-public-tunnel>/webhook/razorpay` (use `ngrok http 8000` or similar, since Razorpay must reach your local backend)
   - Active events: `payment.captured`, `payment.failed`
   - Copy the generated **Webhook Secret**

## 1. Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
copy .env.example .env        # Windows: copy, macOS/Linux: cp
```

Edit `backend/.env` and fill in `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
`RAZORPAY_WEBHOOK_SECRET` with the test-mode values from above.

Run it:

```bash
uvicorn app.main:app --reload --port 8000
```

Tables (`products`, `orders`, `audit_logs`) are created automatically on
startup via SQLAlchemy against `backend/app.db` (SQLite).

## 2. Policy-gate setup

Separate virtual environment, separate process, separate port — this is
deliberate (see Level 2 decision on gate placement). It does nothing but
answer `/health` in this phase.

```bash
cd policy-gate
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

uvicorn app.main:app --reload --port 8001
```

Verify: `curl http://localhost:8001/health` → `{"status": "ok"}`

## 3. Frontend setup

```bash
cd frontend
npm install
copy .env.local.example .env.local
npm run dev
```

Opens on `http://localhost:5173` by default.

## Manual end-to-end test (do this before considering Phase 1 done)

1. With `backend` running, seed a product:
   ```bash
   curl -X POST http://localhost:8000/product ^
     -H "Content-Type: application/json" ^
     -d "{\"name\": \"Test Widget\", \"price\": 50000, \"stock\": 10, \"description\": \"A test product\"}"
   ```
   (`price` is in paise — `50000` = ₹500.00)
2. Open the frontend — confirm the product appears in the catalog.
3. Click **Buy** — the Razorpay checkout widget should open.
4. Pay using a [Razorpay test card](https://razorpay.com/docs/payments/payments/test-card-upi-details/)
   (e.g. `4111 1111 1111 1111`, any future expiry, any CVV).
5. Confirm the frontend shows "Payment initiated".
6. Confirm the webhook fired (check backend logs / your tunnel) and that the
   matching row in `orders` (in `backend/app.db`) now has `status = "paid"`.
7. Independently, confirm `policy-gate` is up: `curl http://localhost:8001/health`.

## What's deliberately NOT in Phase 1

- No LLM / LangGraph / agent reasoning
- No negotiation or discount logic
- No policy-gate decision logic (`/evaluate` etc.) — only `/health`
- No hash-chaining logic (the `audit_logs` table has `previous_hash` /
  `entry_hash` columns already, but nothing populates them yet)
- No buyer agent, no x402-shaped responses
- No authentication/login
