import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import razorpay
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import gate_client
from app.audit import write_audit_log
from app.auth import AuthUser, optional_user
from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.order import Order
from app.models.product import Product
from app.models.webhook_event import WebhookEvent
from app.schemas.negotiation import AuditLogEntry
from app.schemas.order import OrderConfirmRequest, OrderCreateRequest, OrderCreateResponse

router = APIRouter()
logger = logging.getLogger(__name__)

razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _create_razorpay_order(db: Session, amount: int) -> dict:
    """The one call site that talks to Razorpay's real API. Phase 18.5:
    if it fails (down/slow/timeout — third-party flakiness, not this
    project's own bug) AND DEMO_FALLBACK_MODE is on, a synthetic order is
    substituted so a live demo can keep going. The fallback order id is
    unmistakably fake (`order_DEMOFALLBACK...`, never a shape Razorpay
    itself would produce) and every use is written to the audit log as
    its own event type — this must never be confused with, or mistaken
    for evidence of, a real payment.
    """
    try:
        return razorpay_client.order.create({"amount": amount, "currency": "INR", "payment_capture": 1})
    except Exception as e:
        if not settings.DEMO_FALLBACK_MODE:
            raise
        logger.warning("Razorpay order.create() failed, using DEMO_FALLBACK_MODE synthetic order: %s", e)
        write_audit_log(
            db,
            order_id=None,
            event_type="razorpay_fallback_used",
            payload={"amount": amount, "error": str(e)},
        )
        return {"id": f"order_DEMOFALLBACK{uuid.uuid4().hex[:14]}"}


def create_order_with_optional_discount(
    db: Session,
    product_id: int,
    quantity: int,
    approval_token: Optional[str],
    channel: str = "human",
    buyer_agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    user: Optional[AuthUser] = None,
) -> Order:
    """The ONE place that creates a real Razorpay order + Order row.

    Reused by /order/create (human checkout) and /agent/v1/pay (agent-buyer
    checkout) — no separate, weaker verification path for either channel.
    Default is always the full listed price; a discount is ONLY ever
    applied if approval_token independently verifies against the gate's
    own record — never from anything the caller claims directly. No token,
    an invalid token, or mismatched terms all fall through to this same
    default, silently — never an error, never the caller's requested amount.

    channel/buyer_agent_id are attribution ONLY (Phase 6's dashboard) — they
    never affect the amount or whether a discount applies.
    """
    if idempotency_key:
        existing = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        if existing is not None:
            return existing

    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")

    # Early, honest rejection — but NOT the point of authority: stock is
    # actually deducted atomically only when the order becomes paid (see
    # mark_order_paid), so two concurrent checkouts that both pass this
    # read can't both take the last unit; the second one's deduction fails
    # and is recorded, rather than stock going negative.
    if product.stock < quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    amount = product.price * quantity
    session_id_for_audit = None
    discount_applied = False
    approval_id = None

    if approval_token:
        # requester_id is None for the human channel (no buyer identity
        # exists there — the gate never enforces a match against None on
        # its side, see policy-gate's verify()), and buyer_agent_id for
        # the agent channel — this is the Phase 8 fix for cross-buyer
        # token theft (see red-team-agent's token_replay_variants report).
        # session_id closes the human-channel analog of that same gap
        # (redteam's tampering.py, "session_id_substitution") — None for
        # the agent channel, which has no session_id concept.
        verify_data = gate_client.verify_token(
            approval_token, product_id, quantity, requester_id=buyer_agent_id, session_id=session_id
        )
        if verify_data.get("valid"):
            amount = verify_data["final_amount"]
            session_id_for_audit = verify_data.get("session_id")
            discount_applied = True
            approval_id = verify_data.get("approval_id")
        else:
            write_audit_log(
                db,
                order_id=None,
                event_type="checkout_token_rejected",
                payload={
                    "session_id": None,
                    "channel": channel,
                    "buyer_agent_id": buyer_agent_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "reason": verify_data.get("reason"),
                    "charged_original_price": amount,
                },
            )

    razorpay_order = _create_razorpay_order(db, amount)

    order = Order(
        razorpay_order_id=razorpay_order["id"],
        product_id=product.id,
        amount=amount,
        status="created",
        channel=channel,
        buyer_agent_id=buyer_agent_id,
        idempotency_key=idempotency_key,
        user_id=user.sub if user else None,
        user_email=user.email if user else None,
        quantity=quantity,
        unit_price=product.price,
        approval_id=approval_id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    write_audit_log(
        db,
        order_id=order.id,
        event_type="order_created",
        payload={
            "session_id": session_id_for_audit,
            "channel": channel,
            "buyer_agent_id": buyer_agent_id,
            "user_id": user.sub if user else None,
            "product_id": product.id,
            "quantity": quantity,
            "unit_price": product.price,
            "stock_at_creation": product.stock,
            "amount": amount,
            "discount_applied": discount_applied,
            "approval_id": approval_id,
            "razorpay_order_id": order.razorpay_order_id,
        },
    )

    return order


FULFILLMENT_INITIAL = "placed"


def mark_order_paid(db: Session, order: Order, razorpay_payment_id: str, source: str) -> None:
    """The ONE place an order transitions to paid — used by both the
    client-side /order/confirm path and the webhook path, so stock is
    deducted exactly once per order no matter which arrives first (or
    both). Deduction is a single atomic UPDATE guarded by `stock >= qty`,
    so concurrent payments for the last unit can't drive stock negative:
    the loser's UPDATE matches zero rows and is recorded as a
    stock_deduction_failed audit event for the merchant to resolve — the
    payment itself is already captured by Razorpay and is never silently
    hidden. Callers must have already verified the Razorpay signature.
    """
    if order.status == "paid":
        return
    order.status = "paid"
    order.razorpay_payment_id = razorpay_payment_id
    order.paid_at = datetime.now(timezone.utc)
    order.fulfillment_status = FULFILLMENT_INITIAL
    db.commit()

    deducted = (
        db.query(Product)
        .filter(Product.id == order.product_id, Product.stock >= order.quantity)
        .update({Product.stock: Product.stock - order.quantity}, synchronize_session=False)
    )
    db.commit()
    write_audit_log(
        db,
        order_id=order.id,
        event_type="payment_verified",
        payload={
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "amount": order.amount,
            "source": source,
            "signature_verified": True,
        },
    )
    write_audit_log(
        db,
        order_id=order.id,
        event_type="stock_deducted" if deducted else "stock_deduction_failed",
        payload={"product_id": order.product_id, "quantity": order.quantity, "deducted": bool(deducted)},
    )
    write_audit_log(
        db,
        order_id=order.id,
        event_type="order_status_updated",
        payload={"from": None, "to": FULFILLMENT_INITIAL, "actor": "system"},
    )


@router.post("/order/create", response_model=OrderCreateResponse)
def create_order(
    payload: OrderCreateRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: AuthUser | None = Depends(optional_user),
):
    order = create_order_with_optional_discount(
        db,
        payload.product_id,
        payload.quantity,
        payload.approval_token,
        channel="human",
        session_id=payload.session_id,
        idempotency_key=idempotency_key,
        user=user,
    )
    return OrderCreateResponse(
        razorpay_order_id=order.razorpay_order_id,
        amount=order.amount,
        key_id=settings.RAZORPAY_KEY_ID,
        order_id=order.id,
    )


@router.post("/order/confirm")
def confirm_order(payload: OrderConfirmRequest, db: Session = Depends(get_db)):
    """Phase 18.6 — found live during a submission-readiness audit: this
    backend previously had NO way to learn a payment succeeded other than
    a real Razorpay webhook delivery, which needs a public tunnel this
    project has never actually had running. Every "paid" order in this
    project's entire history turned out to be a redteam test script
    directly simulating a webhook call, not a real payment completing
    normally — a judge completing a real payment during a live demo would
    never see it reflected on the dashboard. This is the fix: called by
    the frontend the moment Razorpay's own checkout.js reports success,
    verified with the SAME HMAC mechanism the webhook path already uses
    (never trusted from the client alone) via
    razorpay_client.utility.verify_payment_signature.
    """
    order = db.query(Order).filter(Order.razorpay_order_id == payload.razorpay_order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    if order.status != "paid":
        write_audit_log(
            db,
            order_id=order.id,
            event_type="order_confirmed_client_side",
            payload={
                "razorpay_payment_id": payload.razorpay_payment_id,
                "note": "Confirmed via verified checkout.js callback, not a webhook — see this endpoint's own docstring.",
            },
        )
        mark_order_paid(db, order, payload.razorpay_payment_id, source="checkout_callback")

    return {"status": order.status, "order_id": order.id}


# Read-only, order-scoped view onto the SAME audit_logs table
# /negotiate/{session_id}/audit already reads — this is the complement
# for events tagged with an order_id rather than a session_id (see
# order_created/order_confirmed_client_side above and
# agent_payment_completed in agent_commerce.py), so a frontend
# "Authorization Lifecycle" view can show the final payment-confirmation
# step, which never carries a session_id in its own payload.
@router.get("/order/{order_id}/audit", response_model=list[AuditLogEntry])
def get_order_audit(order_id: int, db: Session = Depends(get_db)):
    rows = db.query(AuditLog).filter(AuditLog.order_id == order_id).order_by(AuditLog.created_at, AuditLog.id).all()
    entries = []
    for row in rows:
        try:
            payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            continue
        entries.append(AuditLogEntry(id=row.id, event_type=row.event_type, payload=payload, created_at=row.created_at, order_id=row.order_id))
    return entries


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        razorpay_client.utility.verify_webhook_signature(
            body.decode("utf-8"), signature, settings.RAZORPAY_WEBHOOK_SECRET
        )
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = json.loads(body)
    event_type = event.get("event")
    event_id = event.get("id") or event.get("event_id")
    event_created_at = event.get("created_at")
    if event_created_at and int(time.time()) - int(event_created_at) > 86400:
        raise HTTPException(status_code=400, detail="Stale webhook event")
    if event_id:
        db.add(WebhookEvent(provider="razorpay", event_id=event_id, event_type=event_type))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"status": "ok", "duplicate": True}

    try:
        payment_entity = event["payload"]["payment"]["entity"]
        razorpay_order_id = payment_entity["order_id"]
        razorpay_payment_id = payment_entity["id"]

        order = db.query(Order).filter(Order.razorpay_order_id == razorpay_order_id).first()
        if order is not None:
            if event_type == "payment.captured":
                mark_order_paid(db, order, razorpay_payment_id, source="webhook")
            elif event_type == "payment.failed" and order.status != "paid":
                # Red-team-confirmed gap (red-team-agent's webhook_replay.py,
                # "Stale/out-of-order webhook replay"): Razorpay webhooks
                # are not guaranteed to arrive in order, and a delayed
                # redelivery of an earlier failed attempt could arrive
                # AFTER the real payment.captured for the same order —
                # reproduced live, order.status regressed from "paid" back
                # to "failed". "paid" is a terminal success state; a later
                # payment.failed can only be describing an earlier attempt,
                # never something that should undo a real capture.
                order.status = "failed"
                order.razorpay_payment_id = razorpay_payment_id
                db.commit()
                write_audit_log(
                    db,
                    order_id=order.id,
                    event_type="payment_failed",
                    payload={"razorpay_order_id": razorpay_order_id, "razorpay_payment_id": razorpay_payment_id, "source": "webhook"},
                )
    except Exception:
        # Never let internal processing errors block the 200 — avoids Razorpay retry pileup.
        logger.exception("Failed to process Razorpay webhook event %s", event_type)

    return {"status": "ok"}
