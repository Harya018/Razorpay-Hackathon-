"""Merchant order management — admin-gated at the router level, same as
/dashboard/*. Reads use the shared order_detail builder (full view,
including raw event payloads and customer contact). The only write is
the fulfillment-status transition, which is forward-only, persisted on
the Order row, AND written to the hash-chained audit log with the
acting merchant's identity — so every status change is timestamped and
attributable, never a silent column flip.
"""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import write_audit_log
from app.auth import AuthUser, require_merchant_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.order import Order
from app.models.product import Product
from app.order_detail import FULFILLMENT_STEPS, build_order_detail, order_list_item

router = APIRouter(prefix="/dashboard", dependencies=[Depends(require_merchant_admin)])


@router.get("/orders")
def list_orders(db: Session = Depends(get_db), status: str | None = Query(default=None), limit: int = Query(default=100, le=500)):
    q = db.query(Order)
    if status:
        q = q.filter(Order.status == status)
    orders = q.order_by(Order.id.desc()).limit(limit).all()
    products = {p.id: p for p in db.query(Product).all()}
    return [order_list_item(db, o, products) for o in orders]


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return build_order_detail(db, order, for_customer=False)


class StatusUpdate(BaseModel):
    status: Literal["placed", "processing", "shipped", "out_for_delivery", "delivered"]


@router.patch("/orders/{order_id}/status")
def update_fulfillment_status(order_id: int, payload: StatusUpdate, user: AuthUser = Depends(require_merchant_admin), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "paid":
        raise HTTPException(status_code=409, detail="Only paid orders have a fulfillment lifecycle")
    current = order.fulfillment_status or "placed"
    if FULFILLMENT_STEPS.index(payload.status) <= FULFILLMENT_STEPS.index(current):
        raise HTTPException(status_code=409, detail=f"Cannot move from '{current}' back to '{payload.status}' — the lifecycle is forward-only")
    previous = order.fulfillment_status
    order.fulfillment_status = payload.status
    db.commit()
    write_audit_log(
        db,
        order_id=order.id,
        event_type="order_status_updated",
        payload={"from": previous, "to": payload.status, "actor": user.email or user.sub},
    )
    return {"order_id": order.id, "fulfillment_status": order.fulfillment_status}


_PAYMENT_EVENT_TYPES = ("order_created", "payment_verified", "payment_failed", "order_confirmed_client_side", "checkout_token_rejected", "razorpay_fallback_used", "stock_deduction_failed")


@router.get("/payments")
def payment_logs(db: Session = Depends(get_db), outcome: Literal["all", "successful", "failed", "pending"] = "all", limit: int = Query(default=200, le=1000)):
    """Real payment-related audit events joined to their order row. Filtering
    is by the ORDER's current status (successful=paid, failed=failed,
    pending=created), since that is the backend's authoritative record of
    the payment's outcome — never inferred from event names alone.
    """
    rows = db.query(AuditLog).filter(AuditLog.event_type.in_(_PAYMENT_EVENT_TYPES)).order_by(AuditLog.id.desc()).limit(limit).all()
    order_ids = {r.order_id for r in rows if r.order_id is not None}
    orders = {o.id: o for o in db.query(Order).filter(Order.id.in_(order_ids)).all()} if order_ids else {}
    wanted = {"successful": "paid", "failed": "failed", "pending": "created"}.get(outcome)

    out = []
    for r in rows:
        order = orders.get(r.order_id)
        if wanted and (order is None or order.status != wanted):
            continue
        try:
            payload = json.loads(r.payload) if r.payload else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        out.append(
            {
                "id": r.id,
                "timestamp": r.created_at.isoformat(),
                "event": r.event_type,
                "order_id": r.order_id,
                "order_ref": f"ORD-{r.order_id:04d}" if r.order_id else None,
                "razorpay_order_id": order.razorpay_order_id if order else payload.get("razorpay_order_id"),
                "razorpay_payment_id": order.razorpay_payment_id if order else payload.get("razorpay_payment_id"),
                "amount": order.amount if order else payload.get("amount"),
                "order_status": order.status if order else None,
                "verified": order.status == "paid" if order else False,
                "source": payload.get("source") or payload.get("channel") or "backend",
            }
        )
    return out
