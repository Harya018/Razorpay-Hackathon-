from fastapi import FastAPI

from app.database import Base, engine, run_migrations
from app.models import approval  # noqa: F401 — ensures Approval registers on Base.metadata
from app.routes import evaluate, health

# Real decision logic as of Phase 3: /evaluate re-derives every decision
# from merchant_rules.py, never trusts a number the seller agent hands it,
# and never calls an LLM. This service has its own DB file, separate from
# the backend's — that boundary is load-bearing, not cosmetic.
Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="Bounded Agentic Checkout — Policy Gate")

app.include_router(health.router)
app.include_router(evaluate.router)


@app.get("/")
def root():
    return {"service": "policy-gate", "status": "ok"}
