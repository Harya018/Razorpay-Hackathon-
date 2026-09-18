"""Admin-only rule management — lets a merchant adjust the Policy Gate's
discount limits without touching code. This is the ONLY part of the
policy-gate service that is mutated from outside; evaluate.py's actual
decision logic (routes/evaluate.py) is completely untouched by anything
here — these endpoints only change the CONFIGURATION that evaluate.py
already reads via merchant_rules.get_rule()/get_max_attempts().

Unlike /evaluate and /verify (deliberately public/unauthenticated —
they're safe because they're self-verifying and side-effect-bounded),
these endpoints can rewrite the merchant's actual policy, so they are
gated behind the same GATE_SECRET the backend and policy-gate already
share (previously only used to mint approval tokens) — a second,
reasonable use of the one secret these two services already trust each
other with, not a new trust mechanism. Only the backend is expected to
call this, after its own require_merchant_admin has verified a real,
Supabase-signed merchant session — this service still has no concept of
user identity itself, consistent with "auth belongs in the human-facing
app, not the deterministic authorization engine."
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.gate_config import GateConfig, ProductRuleOverride
from app.rules import merchant_rules

router = APIRouter(prefix="/rules")


def _require_gate_secret(x_gate_secret: Optional[str] = Header(default=None)) -> None:
    if not settings.GATE_SECRET:
        # Fail closed: an unconfigured secret must never mean "anyone may
        # rewrite the merchant's discount policy."
        raise HTTPException(status_code=503, detail="GATE_SECRET is not configured")
    if not x_gate_secret or x_gate_secret != settings.GATE_SECRET:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Gate-Secret")


class DefaultRuleUpdate(BaseModel):
    max_discount_pct: float = Field(ge=0, le=100)
    max_attempts: int = Field(ge=1, le=20)


class ProductRuleUpdate(BaseModel):
    max_discount_pct: float = Field(ge=0, le=100)
    floor_price: Optional[int] = Field(default=None, ge=0)  # paise, per unit


def _serialize_default(config: GateConfig) -> dict:
    return {
        "max_discount_pct": config.default_max_discount_pct,
        "max_attempts": config.max_attempts,
        "updated_at": config.updated_at.isoformat(),
    }


def _serialize_product(row: ProductRuleOverride) -> dict:
    return {
        "product_id": row.product_id,
        "max_discount_pct": row.max_discount_pct,
        "floor_price": row.floor_price,
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("", dependencies=[Depends(_require_gate_secret)])
def get_rules(db: Session = Depends(get_db)):
    config = merchant_rules.get_config(db)
    overrides = db.query(ProductRuleOverride).order_by(ProductRuleOverride.product_id).all()
    return {
        "default": _serialize_default(config),
        "products": [_serialize_product(row) for row in overrides],
    }


@router.put("/default", dependencies=[Depends(_require_gate_secret)])
def update_default_rule(payload: DefaultRuleUpdate, db: Session = Depends(get_db)):
    config = merchant_rules.get_config(db)
    config.default_max_discount_pct = payload.max_discount_pct
    config.max_attempts = payload.max_attempts
    db.commit()
    db.refresh(config)
    return _serialize_default(config)


@router.put("/product/{product_id}", dependencies=[Depends(_require_gate_secret)])
def update_product_rule(product_id: int, payload: ProductRuleUpdate, db: Session = Depends(get_db)):
    row = db.query(ProductRuleOverride).filter(ProductRuleOverride.product_id == product_id).first()
    if row is None:
        row = ProductRuleOverride(product_id=product_id, max_discount_pct=payload.max_discount_pct, floor_price=payload.floor_price)
        db.add(row)
    else:
        row.max_discount_pct = payload.max_discount_pct
        row.floor_price = payload.floor_price
    db.commit()
    db.refresh(row)
    return _serialize_product(row)


@router.delete("/product/{product_id}", dependencies=[Depends(_require_gate_secret)])
def delete_product_rule(product_id: int, db: Session = Depends(get_db)):
    row = db.query(ProductRuleOverride).filter(ProductRuleOverride.product_id == product_id).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return {"product_id": product_id, "reverted_to_default": True}
