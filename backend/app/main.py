from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.models import audit_log, order, product  # noqa: F401 — ensures tables register on Base.metadata
from app.routes import catalog, payments

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bounded Agentic Checkout — Backend (Phase 1)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(payments.router)


@app.get("/")
def root():
    return {"service": "backend", "status": "ok"}
