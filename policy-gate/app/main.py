from fastapi import FastAPI

from app.routes import health

# This service is intentionally minimal in Phase 1: it exists to prove the
# policy gate is a real, independently-running service with its own port
# and entrypoint, not a function the seller-side backend calls in-process.
# Decision logic (/evaluate, discount caps, stock checks) is Phase 3.
app = FastAPI(title="Bounded Agentic Checkout — Policy Gate (Phase 1 stub)")

app.include_router(health.router)


@app.get("/")
def root():
    return {"service": "policy-gate", "status": "ok"}
