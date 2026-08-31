# Independent Buyer Agent (Phase 4b)

A standalone LangGraph agent that shops against the seller's
[agent-commerce interface](../docs/agent-commerce-interface.md) — no
shared code, no shared venv, no insider knowledge of the seller's
backend. Everything this agent knows about the seller comes from that
one document.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env
```

You need a buyer identity before running anything — this is a real
onboarding step, not a shortcut:

```bash
curl -X POST http://localhost:8010/agent/v1/register ^
  -H "Content-Type: application/json" ^
  -d "{\"buyer_agent_id\": \"your-bot-name\", \"display_name\": \"Your Bot\"}"
```

Copy the returned `api_key` into `.env` as `BUYER_API_KEY` (and
`buyer_agent_id` as `BUYER_AGENT_ID`). Also set `GROQ_API_KEY` — this
agent's own LLM credentials, separate from the seller's.

## Run

```bash
python -m app.main "a warm-toned lamp under 3500 rupees"
python -m app.main "wireless headphones" --aggressive   # test harness: force an unreasonable ask
```

The seller backend, policy-gate, and frontend don't need to be running
for anything except the seller backend — this agent never talks to the
policy-gate or frontend directly, only to `/agent/v1/*` on the backend.

## What "independent" means here, concretely

- No file in this directory imports anything from `/backend`.
- This venv has no `razorpay` package installed (a backend-only
  dependency) and no access to `/backend`'s `app` package — verified by
  attempting both imports and confirming `ModuleNotFoundError`.
- `app/client.py` was written by reading
  `docs/agent-commerce-interface.md` only.
- `app/llm.py` is its own structured-output implementation, not a copy
  of the seller agent's — any resemblance is convergent design.

See `../docs/agent-commerce-interface.md` for the interface contract and
its revision notes for the gaps found while building this agent.
