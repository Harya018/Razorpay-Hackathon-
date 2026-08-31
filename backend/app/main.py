from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine, run_migrations
from app.models import audit_log, buyer_agent, order, product, purchase_intent  # noqa: F401 — ensures tables register on Base.metadata
from app.routes import agent_commerce, catalog, dashboard, negotiation, payments

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="Bounded Agentic Checkout — Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(payments.router)
app.include_router(negotiation.router)
app.include_router(agent_commerce.router)
app.include_router(dashboard.router)


@app.get("/")
def root():
    return {"service": "backend", "status": "ok"}
