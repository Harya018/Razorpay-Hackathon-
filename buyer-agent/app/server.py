"""Phase 10, Part C: FastAPI app exposing this buyer agent's interactive
/shopper/* interface. Run with:

    buyer-agent/.venv/Scripts/python -m uvicorn app.server:app --port 8020

This is ADDITIVE — app/main.py's CLI (`python -m app.main "<goal>"`)
still runs the exact same graph fully autonomously in one shot and is
unaffected by this file existing.
"""

from fastapi import FastAPI

from app.routes import shopper

app = FastAPI(title="Buyer Agent — Shopper Interface")
app.include_router(shopper.router)


@app.get("/")
def root():
    return {"service": "buyer-agent-shopper", "status": "ok"}
