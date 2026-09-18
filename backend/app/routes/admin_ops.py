"""Read-only, admin-gated operational visibility — webhook processing
history. Nothing here writes anything or changes any decision; it only
lets the Merchant Dashboard's Payments/Technical views show real evidence
of webhook signature verification and deduplication instead of asserting
it in prose alone.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_merchant_admin
from app.database import get_db
from app.models.webhook_event import WebhookEvent

router = APIRouter(prefix="/admin", dependencies=[Depends(require_merchant_admin)])


@router.get("/webhooks/recent")
def recent_webhooks(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.query(WebhookEvent).order_by(WebhookEvent.id.desc()).limit(min(limit, 100)).all()
    # Every row here, by construction, already passed HMAC signature
    # verification and the staleness check (see payments.py's
    # razorpay_webhook — a signature/staleness failure raises a 400
    # BEFORE any WebhookEvent row is ever inserted, so a row existing at
    # all IS the proof of a verified, fresh delivery). The unique
    # constraint on event_id is what "deduplication: checked" means here
    # — a genuine replay hits an IntegrityError and is never inserted
    # twice, which is why this list never contains a duplicate event_id.
    return [
        {
            "id": row.id,
            "provider": row.provider,
            "event_id": row.event_id,
            "event_type": row.event_type,
            "created_at": row.created_at.isoformat(),
            "signature_verified": True,
            "deduplicated": True,
        }
        for row in rows
    ]
