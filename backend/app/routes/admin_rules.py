"""Merchant-facing proxy onto policy-gate's admin-only /rules endpoints.

This is the ONLY place a discount policy value can be changed from the
app, and it's a thin proxy, not a second implementation: every request
here is forwarded to policy-gate's own POST/PUT/DELETE /rules routes
(app/routes/rules.py over there), which are the actual source of truth
and the actual enforcement point (evaluate.py reads from there on every
negotiation). This file exists only because policy-gate has no concept of
a signed-in merchant identity by design (see auth.py's module docstring
principle: "auth belongs in the human-facing app, not the deterministic
authorization engine") — require_merchant_admin below is the real,
Supabase-verified check; policy-gate's own X-Gate-Secret check is a
second, independent layer that stops anyone who can merely reach
policy-gate's port (bypassing this backend entirely) from rewriting the
merchant's policy.
"""

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_merchant_admin
from app.config import settings
from app.database import get_db
from app.models.product import Product

router = APIRouter(prefix="/admin/policy-rules", dependencies=[Depends(require_merchant_admin)])


class DefaultRuleUpdate(BaseModel):
    max_discount_pct: float = Field(ge=0, le=100)
    max_attempts: int = Field(ge=1, le=20)


class ProductRuleUpdate(BaseModel):
    max_discount_pct: float = Field(ge=0, le=100)
    floor_price: int | None = Field(default=None, ge=0)


def _headers() -> dict:
    if not settings.GATE_SECRET:
        raise HTTPException(status_code=503, detail="GATE_SECRET is not configured on the backend")
    return {"X-Gate-Secret": settings.GATE_SECRET}


def _forward(method: str, path: str, json: dict | None = None) -> dict:
    try:
        resp = requests.request(method, f"{settings.POLICY_GATE_URL}{path}", json=json, headers=_headers(), timeout=5)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Policy Gate is unreachable") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


@router.get("")
def get_rules(db: Session = Depends(get_db)):
    data = _forward("GET", "/rules")
    # Enrich with product names for display — policy-gate has no catalog
    # of its own by design, so this join happens here, not there.
    names = {p.id: p.name for p in db.query(Product).all()}
    for row in data["products"]:
        row["product_name"] = names.get(row["product_id"])
    # Also surface every catalog product so the admin can add an override
    # to one that doesn't have one yet, not just edit existing ones.
    overridden_ids = {row["product_id"] for row in data["products"]}
    data["catalog"] = [
        {"product_id": p.id, "name": p.name, "price": p.price, "has_override": p.id in overridden_ids}
        for p in db.query(Product).order_by(Product.id).all()
    ]
    return data


@router.put("/default")
def update_default_rule(payload: DefaultRuleUpdate):
    return _forward("PUT", "/rules/default", payload.model_dump())


@router.put("/product/{product_id}")
def update_product_rule(product_id: int, payload: ProductRuleUpdate):
    return _forward("PUT", f"/rules/product/{product_id}", payload.model_dump())


@router.delete("/product/{product_id}")
def delete_product_rule(product_id: int):
    return _forward("DELETE", f"/rules/product/{product_id}")
