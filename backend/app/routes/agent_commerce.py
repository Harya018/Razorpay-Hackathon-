import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import gate_client
from app.agent import prompts as negotiation_prompts
from app.agent.nodes import AgentNegotiationMessageOutput, StructuredOutputError, _call_structured
from app.agent_auth import generate_api_key, hash_api_key, require_buyer_agent
from app.agent_commerce.schemas import DiscoveryResponse
from app.agent_commerce.x402_headers import (
    MalformedPaymentHeaderError,
    build_payment_required,
    build_payment_response,
    parse_payment_signature,
)
from app.audit import write_audit_log
from app.config import settings
from app.database import get_db
from app.models.buyer_agent import BuyerAgent
from app.models.order import Order
from app.models.product import Product
from app.models.purchase_intent import PurchaseIntent
from app.routes.payments import create_order_with_optional_discount
from app.schemas.agent_commerce import (
    CatalogItem,
    NegotiateRequest,
    NegotiateResponse,
    OrderStatusResponse,
    PayRequest,
    PayResponse,
    PurchaseRequest,
    PurchaseTermsResponse,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter(prefix="/agent/v1")

logger = logging.getLogger(__name__)


def _require_matching_identity(payload_buyer_agent_id: str, buyer: BuyerAgent) -> None:
    if payload_buyer_agent_id != buyer.buyer_agent_id:
        raise HTTPException(
            status_code=403, detail="buyer_agent_id does not match the authenticated identity"
        )


def _to_catalog_item(product: Product) -> CatalogItem:
    return CatalogItem(
        id=product.id,
        name=product.name,
        description=product.description,
        price=product.price,
        stock=product.stock,
        negotiable=True,
    )


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register_buyer_agent(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(BuyerAgent).filter(BuyerAgent.buyer_agent_id == payload.buyer_agent_id).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="buyer_agent_id already registered")

    api_key = generate_api_key()
    buyer = BuyerAgent(
        buyer_agent_id=payload.buyer_agent_id,
        display_name=payload.display_name,
        api_key_hash=hash_api_key(api_key),
    )
    db.add(buyer)
    db.commit()
    db.refresh(buyer)

    return RegisterResponse(buyer_agent_id=buyer.buyer_agent_id, api_key=api_key, created_at=buyer.created_at)


@router.get("/catalog", response_model=list[CatalogItem])
def agent_catalog(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return [_to_catalog_item(p) for p in products]


@router.get("/product/{product_id}", response_model=CatalogItem)
def agent_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _to_catalog_item(product)


@router.get("/discovery", response_model=DiscoveryResponse)
def agent_discovery():
    """Phase 11 — no authentication required, mirrors /catalog's openness.
    A real x402 V2 client fetches this BEFORE transacting to learn what
    scheme/network this catalog accepts, including the fiat-settlement
    disclaimer, without needing this project's own docs. See
    docs/x402-v2-conformance.md.
    """
    return DiscoveryResponse()


@router.post("/negotiate", response_model=NegotiateResponse)
def agent_negotiate(
    payload: NegotiateRequest,
    buyer: BuyerAgent = Depends(require_buyer_agent),
    db: Session = Depends(get_db),
):
    _require_matching_identity(payload.buyer_agent_id, buyer)

    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    session_id = f"agent-negotiate-{uuid.uuid4()}"
    reasoning = (
        f"Proposal from buyer agent '{buyer.buyer_agent_id}' via /agent/v1/negotiate. "
        f'Buyer message: "{payload.message}"'
        if payload.message
        else f"Proposal from buyer agent '{buyer.buyer_agent_id}' via /agent/v1/negotiate."
    )
    offer = {
        "type": payload.proposed_terms.type,
        "value": payload.proposed_terms.value,
        "reasoning": reasoning,
    }

    write_audit_log(
        db,
        order_id=None,
        event_type="agent_negotiate_requested",
        payload={
            "session_id": session_id,
            "buyer_agent_id": buyer.buyer_agent_id,
            "product_id": payload.product_id,
            "quantity": payload.quantity,
            "proposed_terms": offer,
        },
    )

    gate_response = gate_client.evaluate(
        session_id=session_id,
        product_id=payload.product_id,
        cart_quantity=payload.quantity,
        original_price=product.price,
        proposed_offer=offer,
        attempt_number=1,
        requester_id=buyer.buyer_agent_id,
    )

    write_audit_log(
        db,
        order_id=None,
        event_type="agent_negotiate_decided",
        payload={
            "session_id": session_id,
            "buyer_agent_id": buyer.buyer_agent_id,
            "approved": gate_response.get("approved"),
            "reason": gate_response.get("reason"),
            "max_allowed": gate_response.get("max_allowed"),
            "final_terms": gate_response.get("final_terms"),
        },
    )

    # Phase 11 — best-effort natural-language framing of the decision
    # ABOVE, which is already final by this point. This call can only
    # produce a `message` string; it has no way to influence approved,
    # reason, max_allowed, or final_terms, all of which are already set
    # from gate_response. If the LLM call fails for any reason, message
    # stays None and every other field in the response is unaffected —
    # mirrors close_negotiation's best-effort customer_mindset_summary.
    #
    # Only attempted when the caller sent its own message — found during
    # Phase 11's red-team pass: an unconditional LLM round-trip on every
    # /negotiate call added real latency (and, under concurrent load, real
    # flakiness from Groq/Gemini rate-limit fallback chains) for every
    # caller, including deterministic/automated ones that never asked for
    # a chat reply. A buyer that didn't open a conversation doesn't need
    # one back — this keeps a plain proposed_terms-only call exactly as
    # fast and dependency-free as it was before Phase 11.
    reply_message: Optional[str] = None
    if payload.message is not None:
        try:
            final_terms = gate_response.get("final_terms") or {}
            reply = _call_structured(
                system=negotiation_prompts.agent_negotiation_message_system(),
                user=negotiation_prompts.agent_negotiation_message_user(
                    product_name=product.name,
                    listed_unit_price=product.price,
                    quantity=payload.quantity,
                    buyer_message=payload.message,
                    proposed_value=payload.proposed_terms.value,
                    approved=bool(gate_response.get("approved")),
                    reason=gate_response.get("reason"),
                    max_allowed=gate_response.get("max_allowed"),
                    final_value=final_terms.get("value"),
                ),
                schema=AgentNegotiationMessageOutput,
            )
            reply_message = reply.message
        except StructuredOutputError as e:
            logger.warning("agent_negotiation_message skipped for session %s: %s", session_id, e)

    return NegotiateResponse(
        approved=gate_response.get("approved", False),
        approval_token=gate_response.get("approval_token"),
        final_terms=gate_response.get("final_terms"),
        reason=gate_response.get("reason"),
        max_allowed=gate_response.get("max_allowed"),
        message=reply_message,
    )


@router.post("/purchase", response_model=PurchaseTermsResponse, status_code=402)
def agent_purchase(
    payload: PurchaseRequest,
    response: Response,
    buyer: BuyerAgent = Depends(require_buyer_agent),
    db: Session = Depends(get_db),
):
    _require_matching_identity(payload.buyer_agent_id, buyer)

    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.stock < payload.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    amount = product.price * payload.quantity
    terms_reference = str(uuid.uuid4())

    intent = PurchaseIntent(
        terms_reference=terms_reference,
        buyer_agent_id=buyer.buyer_agent_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        declared_approval_token=payload.approval_token,
        used=False,
    )
    db.add(intent)
    db.commit()

    write_audit_log(
        db,
        order_id=None,
        event_type="agent_purchase_402",
        payload={
            "session_id": None,
            "buyer_agent_id": buyer.buyer_agent_id,
            "product_id": payload.product_id,
            "quantity": payload.quantity,
            "quoted_amount": amount,
            "terms_reference": terms_reference,
            "declared_approval_token_present": payload.approval_token is not None,
        },
    )

    # x402 V2 wire-format layer (Phase 8) — additive, on top of the JSON
    # body above, which remains unchanged for Phase 4a/4b backward
    # compatibility. See docs/agent-commerce-interface.md, "x402 V2
    # Conformance and Its Limits", for what these fields actually mean
    # for a Razorpay/INR settlement backend.
    _, encoded_header = build_payment_required(
        resource_url=f"/agent/v1/product/{product.id}",
        resource_description=f"Purchase of {payload.quantity} x {product.name}",
        amount_paise=amount,
        pay_to=settings.RAZORPAY_KEY_ID,
        product_id=product.id,
        quantity=payload.quantity,
        terms_reference=terms_reference,
    )
    response.headers["PAYMENT-REQUIRED"] = encoded_header

    return PurchaseTermsResponse(amount=amount, terms_reference=terms_reference)


@router.post("/pay", response_model=PayResponse)
def agent_pay(
    payload: PayRequest,
    response: Response,
    buyer: BuyerAgent = Depends(require_buyer_agent),
    db: Session = Depends(get_db),
    payment_signature: Optional[str] = Header(default=None, alias="PAYMENT-SIGNATURE"),
):
    _require_matching_identity(payload.buyer_agent_id, buyer)

    # x402 V2 wire-format layer — as of Phase 11, PAYMENT-SIGNATURE is
    # REQUIRED (Phase 8 made it optional/additive; see
    # docs/x402-v2-conformance.md's "Backward compatibility decision" for
    # exactly why this one header on this one endpoint is the deliberate
    # exception to "everything else stays backward compatible"). The JSON
    # body remains the actual field-level source of truth — the header
    # must independently agree with it (defense in depth), never override
    # it, so this is a stricter gate, not a new way to bypass verification.
    if payment_signature is None:
        raise HTTPException(status_code=400, detail="Missing required PAYMENT-SIGNATURE header")
    try:
        decoded = parse_payment_signature(payment_signature)
    except (MalformedPaymentHeaderError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=f"Malformed PAYMENT-SIGNATURE header: {e}")
    receipt = decoded.payload.custodialReceipt
    if receipt.terms_reference != payload.terms_reference:
        raise HTTPException(
            status_code=400,
            detail="PAYMENT-SIGNATURE header's custodialReceipt.terms_reference does not match the request body",
        )
    if receipt.approval_token != payload.approval_token:
        raise HTTPException(
            status_code=400,
            detail="PAYMENT-SIGNATURE header's custodialReceipt.approval_token does not match the request body",
        )

    intent = db.query(PurchaseIntent).filter(PurchaseIntent.terms_reference == payload.terms_reference).first()
    if intent is None or intent.buyer_agent_id != buyer.buyer_agent_id:
        _, failure_header = build_payment_response(
            success=False,
            payer=buyer.buyer_agent_id,
            transaction="",
            error_reason="unknown_or_already_used_terms_reference",
        )
        # Conformance fix (docs/x402-conformance-diff.md): the real spec's
        # HTTP transport maps BOTH "payment required" and "payment
        # failed" scenarios to 402, not a generic 404 — a settlement
        # failure (this terms_reference is unknown or already used) is
        # exactly a "payment failed" case, so it gets 402 with
        # PAYMENT-RESPONSE attached, matching PAYMENT-REQUIRED's own use
        # of 402 earlier in the same flow. (A malformed/missing
        # PAYMENT-SIGNATURE header, just above, stays 400 — that's a
        # transport-level parse failure, not a payment outcome.)
        raise HTTPException(
            status_code=402,
            detail="Unknown or already-used terms_reference",
            headers={"PAYMENT-RESPONSE": failure_header},
        )

    # Phase 8 fix: claim `used` via a single atomic UPDATE ... WHERE
    # used = 0, not a separate read-then-write — a read-then-write here
    # is a TOCTOU race where two concurrent /pay calls for the SAME
    # terms_reference could both observe used=False before either commits.
    # A red-team concurrency test found the identical anti-pattern
    # exploitable in policy-gate's /verify (see
    # /red-team-agent/results/red_team_report.md, concurrent_race
    # Experiment B — a genuine double-spend); this call site has the same
    # shape, so it's hardened the same way even though this particular
    # attack run happened not to trigger it here (SQLite's own file-level
    # locking is NOT a substitute for an atomic claim — it isn't
    # guaranteed application-level correctness).
    claimed = db.query(PurchaseIntent).filter(
        PurchaseIntent.id == intent.id, PurchaseIntent.used.is_(False)
    ).update({"used": True})
    db.commit()
    if claimed == 0:
        _, failure_header = build_payment_response(
            success=False,
            payer=buyer.buyer_agent_id,
            transaction="",
            error_reason="unknown_or_already_used_terms_reference",
        )
        # Conformance fix (docs/x402-conformance-diff.md): the real spec's
        # HTTP transport maps BOTH "payment required" and "payment
        # failed" scenarios to 402, not a generic 404 — a settlement
        # failure (this terms_reference is unknown or already used) is
        # exactly a "payment failed" case, so it gets 402 with
        # PAYMENT-RESPONSE attached, matching PAYMENT-REQUIRED's own use
        # of 402 earlier in the same flow. (A malformed/missing
        # PAYMENT-SIGNATURE header, just above, stays 400 — that's a
        # transport-level parse failure, not a payment outcome.)
        raise HTTPException(
            status_code=402,
            detail="Unknown or already-used terms_reference",
            headers={"PAYMENT-RESPONSE": failure_header},
        )

    # The SAME order-creation + approval_token verification path Phase 1/3
    # built for the human checkout — no separate, weaker path here.
    order = create_order_with_optional_discount(
        db,
        intent.product_id,
        intent.quantity,
        payload.approval_token,
        channel="agent",
        buyer_agent_id=buyer.buyer_agent_id,
    )

    write_audit_log(
        db,
        order_id=order.id,
        event_type="agent_payment_completed",
        payload={
            "session_id": None,
            "buyer_agent_id": buyer.buyer_agent_id,
            "terms_reference": payload.terms_reference,
            "amount": order.amount,
        },
    )

    # PAYMENT-RESPONSE.transaction is the Razorpay order id — NOT a
    # blockchain transaction hash. See docs/agent-commerce-interface.md.
    _, success_header = build_payment_response(
        success=True,
        payer=buyer.buyer_agent_id,
        transaction=order.razorpay_order_id,
        amount_paise=order.amount,
        extensions={"order_id": order.id, "status": order.status},
    )
    response.headers["PAYMENT-RESPONSE"] = success_header

    return PayResponse(
        order_id=order.id,
        razorpay_order_id=order.razorpay_order_id,
        status=order.status,
        amount=order.amount,
    )


@router.get("/order/{order_id}/status", response_model=OrderStatusResponse)
def agent_order_status(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderStatusResponse(
        order_id=order.id,
        status=order.status,
        amount=order.amount,
        razorpay_order_id=order.razorpay_order_id,
    )
