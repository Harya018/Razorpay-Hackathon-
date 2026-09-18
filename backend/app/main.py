from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine, run_migrations
from app.models import audit_log, buyer_agent, customer_profile, idempotency, order, product, purchase_intent, webhook_event  # noqa: F401 — ensures tables register on Base.metadata
from app.routes import admin_ops, admin_orders, admin_rules, agent_commerce, auth, catalog, dashboard, negotiation, orders, payments, profile

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="Bounded Agentic Checkout — Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(payments.router)
app.include_router(negotiation.router)
app.include_router(agent_commerce.router)
app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(admin_rules.router)
app.include_router(admin_ops.router)
app.include_router(admin_orders.router)
app.include_router(orders.router)
app.include_router(profile.router)


@app.get("/")
def root():
    return {"service": "backend", "status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "backend"}