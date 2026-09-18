import importlib.util
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine, run_migrations
from app.models import audit_log, buyer_agent, customer_profile, idempotency, order, product, purchase_intent, webhook_event  # noqa: F401 — ensures tables register on Base.metadata
from app.routes import admin_ops, admin_orders, admin_rules, agent_commerce, auth, catalog, dashboard, negotiation, orders, payments, profile

logger = logging.getLogger("app.startup")

Base.metadata.create_all(bind=engine)
run_migrations()


def _run_startup_seed_if_enabled() -> None:
    """Optional, production-safe catalog seed for deployments with no shell
    (Render free tier). Reuses scripts/seed_catalog.py's existing seed()
    unchanged — loaded by file path so it works regardless of the
    process's CWD/sys.path. Runs ONLY when SEED_CATALOG_ON_STARTUP is true
    AND the products table is empty; see the setting's comment in
    config.py for why an unconditional run would be destructive. Never
    exposed as an endpoint.
    """
    if not settings.SEED_CATALOG_ON_STARTUP:
        return
    logger.info("Catalog startup seed enabled")
    db = SessionLocal()
    try:
        existing = db.query(product.Product).count()
    finally:
        db.close()
    if existing > 0:
        logger.info("Catalog already populated (%d products) — startup seed skipped; run scripts/seed_catalog.py manually to re-seed", existing)
        return

    seed_path = Path(__file__).resolve().parent.parent / "scripts" / "seed_catalog.py"
    spec = importlib.util.spec_from_file_location("seed_catalog", seed_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed()
    logger.info("Catalog seed completed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Tables/migrations already ran at import time above; seeding happens
    # here, after that, and before the first request is served.
    _run_startup_seed_if_enabled()
    yield


app = FastAPI(title="Bounded Agentic Checkout — Backend", lifespan=lifespan)

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