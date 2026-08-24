import json
import logging

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.order import Order
from app.models.product import Product
from app.schemas.order import OrderCreateRequest, OrderCreateResponse

router = APIRouter()
logger = logging.getLogger(__name__)

razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


@router.post("/order/create", response_model=OrderCreateResponse)
def create_order(payload: OrderCreateRequest, db: Session = Depends(get_db)):
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock < payload.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    amount = product.price * payload.quantity  # paise, integer only

    razorpay_order = razorpay_client.order.create(
        {
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1,
        }
    )

    order = Order(
        razorpay_order_id=razorpay_order["id"],
        product_id=product.id,
        amount=amount,
        status="created",
    )
    db.add(order)
    db.commit()

    return OrderCreateResponse(
        razorpay_order_id=razorpay_order["id"],
        amount=amount,
        key_id=settings.RAZORPAY_KEY_ID,
    )


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
            elif event_type == "payment.failed":
                order.status = "failed"
                order.razorpay_payment_id = razorpay_payment_id
                db.commit()
    except Exception:
        # Never let internal processing errors block the 200 — avoids Razorpay retry pileup.
        logger.exception("Failed to process Razorpay webhook event %s", event_type)

    return {"status": "ok"}
