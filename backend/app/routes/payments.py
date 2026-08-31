import json
import logging
import uuid
from typing import Optional

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import gate_client
from app.audit import write_audit_log
from app.config import settings
from app.database import get_db
from app.models.order import Order
from app.models.product import Product
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
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock < quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    amount = product.price * quantity
    session_id_for_audit = None
    discount_applied = False

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
            "product_id": product.id,
            "quantity": quantity,
            "amount": amount,
            "discount_applied": discount_applied,
        },
    )

    return order


@router.post("/order/create", response_model=OrderCreateResponse)
def create_order(payload: OrderCreateRequest, db: Session = Depends(get_db)):
    order = create_order_with_optional_discount(
        db, payload.product_id, payload.quantity, payload.approval_token, channel="human", session_id=payload.session_id
    )
    return OrderCreateResponse(
        razorpay_order_id=order.razorpay_order_id,
        amount=order.amount,
        key_id=settings.RAZORPAY_KEY_ID,
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
        order.status = "paid"
        order.razorpay_payment_id = payload.razorpay_payment_id
        db.commit()
        write_audit_log(
            db,
            order_id=order.id,
            event_type="order_confirmed_client_side",
            payload={
                "razorpay_payment_id": payload.razorpay_payment_id,
                "note": "Confirmed via verified checkout.js callback, not a webhook — see this endpoint's own docstring.",
            },
        )

    return {"status": order.status}


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

    try:
        payment_entity = event["payload"]["payment"]["entity"]
        razorpay_order_id = payment_entity["order_id"]
        razorpay_payment_id = payment_entity["id"]

        order = db.query(Order).filter(Order.razorpay_order_id == razorpay_order_id).first()
        if order is not None:
            if event_type == "payment.captured":
                order.status = "paid"
                order.razorpay_payment_id = razorpay_payment_id
                db.commit()
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
    except Exception:
        # Never let internal processing errors block the 200 — avoids Razorpay retry pileup.
        logger.exception("Failed to process Razorpay webhook event %s", event_type)

    return {"status": "ok"}
