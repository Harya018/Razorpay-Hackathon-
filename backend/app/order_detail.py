"""One order -> one trace. Assembles everything the audit log and the
orders/products tables already record about a single order into a
structured detail view — summary, payment, policy authorization, the
chronological event list, and the ID chain. Read-only; every field
comes from a real row, and every relationship that ISN'T recorded is
reported as unavailable rather than guessed.

Two audiences share this: the customer who owns the order (a curated
timeline, no raw payloads, no LLM reasoning text) and the merchant (the
full event list with raw payloads). Ownership/role checks happen in the
route layer BEFORE this is called — this module never decides who may
see what, it only shapes what a caller already cleared to see.
"""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.customer_profile import CustomerProfile
from app.models.order import Order
from app.models.product import Product

FULFILLMENT_STEPS = ["placed", "processing", "shipped", "out_for_delivery", "delivered"]
FULFILLMENT_LABELS = {
    "placed": "Order Placed",
    "processing": "Processing",
    "shipped": "Shipped",
    "out_for_delivery": "Out for Delivery",
    "delivered": "Delivered",
}

_ACTOR = {
    "cart_assessed": "seller-agent",
    "offer_decision": "seller-agent",
    "offer_proposed": "seller-agent",
    "response_interpreted": "seller-agent",
    "negotiation_closed": "seller-agent",
    "customer_mindset_summary": "seller-agent",
    "llm_fallback_used": "seller-agent",
    "offer_generation_failed": "seller-agent",
    "gate_call": "policy-gate",
    "gate_decision": "policy-gate",
    "agent_negotiate_requested": "buyer-agent",
    "agent_negotiate_decided": "policy-gate",
    "agent_purchase_402": "buyer-agent",
    "agent_payment_completed": "buyer-agent",
}

# Events whose payloads contain LLM-authored prose — never shown to the
# customer-facing view (no chain-of-thought leaks), merchant sees them.
_INTERNAL_ONLY = {"offer_decision", "customer_mindset_summary", "response_interpreted", "llm_fallback_used", "offer_generation_failed"}


def _load(row: AuditLog) -> dict:
    try:
        payload = json.loads(row.payload) if row.payload else {}
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {
        "id": row.id,
        "event_type": row.event_type,
        "created_at": row.created_at.isoformat(),
        "order_id": row.order_id,
        "actor": _ACTOR.get(row.event_type, "backend"),
        "payload": payload,
        "entry_hash_short": (row.entry_hash or "")[:12],
    }


def _session_events(db: Session, session_id: str) -> list[dict]:
    rows = db.query(AuditLog).order_by(AuditLog.created_at, AuditLog.id).all()
    out = []
    for row in rows:
        e = _load(row)
        if e["payload"].get("session_id") == session_id:
            out.append(e)
    return out


def _order_events(db: Session, order_id: int) -> list[dict]:
    rows = db.query(AuditLog).filter(AuditLog.order_id == order_id).order_by(AuditLog.created_at, AuditLog.id).all()
    return [_load(r) for r in rows]


def _summary_line(e: dict) -> str:
    p = e["payload"]
    t = e["event_type"]
    rupees = lambda v: f"₹{v / 100:.2f}" if isinstance(v, (int, float)) else "—"  # noqa: E731
    if t == "cart_assessed":
        return f"{p.get('quantity')} × {p.get('product_name')} — stock on hand {p.get('stock')}"
    if t == "offer_proposed":
        return f"{p.get('type')} at {rupees(p.get('value'))} (attempt {p.get('attempt_number')})"
    if t == "gate_call":
        return f"sent {rupees((p.get('requested_offer') or {}).get('value'))} to policy-gate"
    if t == "gate_decision":
        return "APPROVED" if p.get("approved") else f"REJECTED — {p.get('reason')}"
    if t == "negotiation_closed":
        return f"{p.get('final_status')} after {p.get('turns')} turn(s)"
    if t == "order_created":
        return f"{rupees(p.get('amount'))} — {'negotiated discount applied' if p.get('discount_applied') else 'list price'}"
    if t == "order_confirmed_client_side":
        return "checkout callback received"
    if t == "payment_verified":
        return f"signature verified ({p.get('source')})"
    if t == "payment_failed":
        return "payment failed"
    if t == "stock_deducted":
        return f"stock −{p.get('quantity')}"
    if t == "stock_deduction_failed":
        return f"could not deduct {p.get('quantity')} — insufficient stock at payment time"
    if t == "order_status_updated":
        return f"{FULFILLMENT_LABELS.get(p.get('to'), p.get('to'))}"
    if t == "checkout_token_rejected":
        return f"token rejected — {p.get('reason')}"
    if t == "agent_payment_completed":
        return f"agent paid {rupees(p.get('amount'))}"
    return t


def build_order_detail(db: Session, order: Order, *, for_customer: bool) -> dict:
    product = db.get(Product, order.product_id)
    order_events = _order_events(db, order.id)
    created = next((e for e in order_events if e["event_type"] == "order_created"), None)
    session_id = created["payload"].get("session_id") if created else None
    session_events = _session_events(db, session_id) if session_id else []

    # ---- summary -----------------------------------------------------------
    unit_price = order.unit_price if order.unit_price is not None else (product.price if product else None)
    list_total = unit_price * order.quantity if unit_price is not None else None
    discount = (list_total - order.amount) if list_total is not None and list_total > order.amount else 0
    summary = {
        "order_id": order.id,
        "order_ref": f"ORD-{order.id:04d}",
        "product": {
            "id": order.product_id,
            "name": product.name if product else f"product {order.product_id}",
            "category": product.category if product else None,
            "image_url": (product.image_urls or [None])[0] if product else None,
            "is_active": product.is_active if product else False,
        },
        "quantity": order.quantity,
        "unit_price": unit_price,
        "list_total": list_total,
        "discount": discount,
        "discount_pct": round(discount / list_total * 100, 1) if list_total else 0,
        "amount": order.amount,
        "currency": "INR",
        "status": order.status,
        "fulfillment_status": order.fulfillment_status,
        "channel": order.channel,
        "buyer_agent_id": order.buyer_agent_id,
        "created_at": order.created_at.isoformat(),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }

    # ---- payment -----------------------------------------------------------
    verified_event = next((e for e in order_events if e["event_type"] == "payment_verified"), None)
    failed_event = next((e for e in order_events if e["event_type"] == "payment_failed"), None)
    payment = {
        "status": order.status,
        "razorpay_order_id": order.razorpay_order_id,
        "razorpay_payment_id": order.razorpay_payment_id,
        "amount": order.amount,
        "currency": "INR",
        "mode": "test",
        "signature_verified": order.status == "paid",
        "verified_at": verified_event["created_at"] if verified_event else None,
        "verification_source": verified_event["payload"].get("source") if verified_event else None,
        "failed_at": failed_event["created_at"] if failed_event else None,
        # Webhook deliveries are stored by Razorpay event id only (no link
        # to an order row is recorded), so per-order webhook status is
        # honestly "not linked" rather than inferred.
        "webhook_status": "not linked to orders by current schema",
    }

    # ---- policy authorization ---------------------------------------------
    gate_decision = next((e for e in reversed(session_events) if e["event_type"] == "gate_decision"), None)
    gate_call = next((e for e in reversed(session_events) if e["event_type"] == "gate_call"), None)
    cart_assessed = next((e for e in session_events if e["event_type"] == "cart_assessed"), None)
    if session_id and gate_decision:
        gp = gate_decision["payload"]
        authoritative = (cart_assessed["payload"]["unit_price"] * cart_assessed["payload"]["quantity"]) if cart_assessed else list_total
        policy = {
            "negotiated": True,
            "session_id": session_id,
            "decision": "approved" if gp.get("approved") else "rejected",
            "reason": gp.get("reason"),
            "requested_price": (gate_call["payload"].get("requested_offer") or {}).get("value") if gate_call else None,
            "authoritative_price": authoritative,
            "approved_price": (gp.get("final_terms") or {}).get("value") if gp.get("approved") else None,
            "max_allowed": gp.get("max_allowed"),
            "discount_pct": summary["discount_pct"],
            "approval_id": order.approval_id,
            "approval_ref": f"auth_{order.approval_id:06d}" if order.approval_id else None,
            "authorized_at": gate_decision["created_at"],
            "redeemed": bool(created and created["payload"].get("discount_applied")),
            "redeemed_at": created["created_at"] if created and created["payload"].get("discount_applied") else None,
        }
    else:
        policy = {"negotiated": False, "note": "List-price order — no Policy Gate authorization was involved."}

    # ---- events / timeline -------------------------------------------------
    all_events = sorted(session_events + [e for e in order_events if e["id"] not in {s["id"] for s in session_events}], key=lambda e: (e["created_at"], e["id"]))
    if for_customer:
        all_events = [e for e in all_events if e["event_type"] not in _INTERNAL_ONLY]
    events = [
        {
            "id": e["id"],
            "event_type": e["event_type"],
            "created_at": e["created_at"],
            "actor": e["actor"],
            "summary": _summary_line(e),
            "related_id": e["order_id"] or e["payload"].get("session_id"),
            "entry_hash_short": e["entry_hash_short"],
            **({} if for_customer else {"payload": e["payload"]}),
        }
        for e in all_events
    ]

    # ---- trace chain -------------------------------------------------------
    trace = [
        {"label": "Product ID", "value": str(order.product_id), "available": True},
        {"label": "Negotiation Session", "value": session_id, "available": bool(session_id), "note": None if session_id else "list-price order, no negotiation"},
        {"label": "Policy Gate Decision", "value": policy["decision"] if policy.get("negotiated") else None, "available": bool(policy.get("negotiated"))},
        {"label": "Approval ID", "value": policy.get("approval_ref"), "available": bool(order.approval_id), "note": None if order.approval_id or not policy.get("negotiated") else "not recorded on orders created before this field existed"},
        {"label": "Order ID", "value": summary["order_ref"], "available": True},
        {"label": "Razorpay Order ID", "value": order.razorpay_order_id, "available": True},
        {"label": "Razorpay Payment ID", "value": order.razorpay_payment_id, "available": bool(order.razorpay_payment_id), "note": None if order.razorpay_payment_id else "no payment captured yet"},
        {"label": "Audit Events", "value": f"{len(events)} hash-chained entries", "available": len(events) > 0},
        {"label": "Fulfillment", "value": FULFILLMENT_LABELS.get(order.fulfillment_status) if order.fulfillment_status else None, "available": bool(order.fulfillment_status), "note": None if order.fulfillment_status else "starts once paid"},
    ]

    detail = {"summary": summary, "payment": payment, "policy": policy, "events": events, "trace": trace, "fulfillment_steps": FULFILLMENT_STEPS, "fulfillment_labels": FULFILLMENT_LABELS}

    if not for_customer:
        profile = db.get(CustomerProfile, order.user_id) if order.user_id else None
        detail["customer"] = {
            "user_id": order.user_id,
            "email": order.user_email,
            "name": profile.display_name if profile else None,
            "phone": profile.phone if profile else None,
            "address_line": profile.address_line if profile else None,
            "city": profile.city if profile else None,
            "pincode": profile.pincode if profile else None,
            "note": None if order.user_id else ("agent-channel order" if order.channel == "agent" else "guest checkout — no signed-in customer"),
        }
    return detail


def order_list_item(db: Session, order: Order, products: dict[int, Product]) -> dict:
    product = products.get(order.product_id)
    return {
        "order_id": order.id,
        "order_ref": f"ORD-{order.id:04d}",
        "product_name": product.name if product else f"product {order.product_id}",
        "product_id": order.product_id,
        "quantity": order.quantity,
        "amount": order.amount,
        "status": order.status,
        "fulfillment_status": order.fulfillment_status,
        "channel": order.channel,
        "customer_email": order.user_email,
        "buyer_agent_id": order.buyer_agent_id,
        "created_at": order.created_at.isoformat(),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "razorpay_order_id": order.razorpay_order_id,
        "razorpay_payment_id": order.razorpay_payment_id,
    }
