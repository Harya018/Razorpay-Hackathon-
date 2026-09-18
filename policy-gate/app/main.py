from fastapi import FastAPI

from app.database import Base, SessionLocal, engine, run_migrations
from app.models import approval, gate_config  # noqa: F401 — ensures models register on Base.metadata
from app.routes import evaluate, health, rules
from app.rules import merchant_rules

# Real decision logic as of Phase 3: /evaluate re-derives every decision
# from merchant_rules.py, never trusts a number the seller agent hands it,
# and never calls an LLM. This service has its own DB file, separate from
# the backend's — that boundary is load-bearing, not cosmetic.
Base.metadata.create_all(bind=engine)
run_migrations()

# One-time seed of the admin-editable rule tables from merchant_rules.py's
# hardcoded initial values — never overwrites an existing row, so this is
# a no-op after the very first startup (see seed_defaults_if_empty).
_seed_db = SessionLocal()
try:
    merchant_rules.seed_defaults_if_empty(_seed_db)
finally:
    _seed_db.close()

app = FastAPI(title="Bounded Agentic Checkout — Policy Gate")

app.include_router(health.router)
app.include_router(evaluate.router)
app.include_router(rules.router)


@app.get("/")
def root():
    return {"service": "policy-gate", "status": "ok"}
