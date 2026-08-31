"""Pure encode/decode helpers for the three x402 V2 headers. No FastAPI,
no DB, no HTTP — these functions only translate between the Pydantic
objects in schemas.py and the base64-JSON string that travels in a
header value, exactly as the spec's HTTP transport describes.
"""

import base64
import json
from typing import Optional

from app.agent_commerce.schemas import (
    EXTENSION_DISCLAIMER,
    CustodialReceipt,
    ExtensionsBlock,
    PaymentPayload,
    PaymentRequired,
    PaymentRequirements,
    ResourceInfo,
    SchemeSpecificPayload,
    SettlementResponse,
)


class MalformedPaymentHeaderError(ValueError):
    """Raised when a header value isn't valid base64, or doesn't decode to
    JSON matching the expected schema. Callers turn this into a 400.
    """


def _encode(model: PaymentPayload | PaymentRequired | SettlementResponse) -> str:
    raw = model.model_dump_json(exclude_none=True, by_alias=True).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _decode_json(header_value: str) -> dict:
    try:
        raw = base64.b64decode(header_value, validate=True)
    except Exception as e:
        raise MalformedPaymentHeaderError(f"header value is not valid base64: {e}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise MalformedPaymentHeaderError(f"decoded header value is not valid JSON: {e}") from e


def build_payment_required(
    *,
    resource_url: str,
    resource_description: str,
    amount_paise: int,
    pay_to: str,
    product_id: int,
    quantity: int,
    terms_reference: str,
) -> tuple[PaymentRequired, str]:
    """Builds the PaymentRequired object + its base64 header value for
    /purchase's 402 response.
    """
    requirements = PaymentRequirements(
        amount=str(amount_paise),
        payTo=pay_to,
        extra={
            "settlementType": "fiat-custodial",
            "facilitator": "razorpay-test-mode",
            "product_id": product_id,
            "quantity": quantity,
            "terms_reference": terms_reference,
        },
    )
    model = PaymentRequired(
        error="Payment required to complete this purchase.",
        resource=ResourceInfo(url=resource_url, description=resource_description),
        accepts=[requirements],
        # Conformance fix (docs/x402-conformance-diff.md): the formal
        # Extensions object (info + schema) was previously never
        # populated — only the informal inr-fiat: network prefix plus a
        # discovery-endpoint disclaimer string existed. Same disclaimer,
        # now also carried in the spec's own mechanism, not just prose.
        extensions=ExtensionsBlock(
            info={"inr-fiat": {"disclaimer": EXTENSION_DISCLAIMER}},
            schema_={
                "type": "object",
                "properties": {"inr-fiat": {"type": "object", "properties": {"disclaimer": {"type": "string"}}}},
            },
        ),
    )
    return model, _encode(model)


def build_payment_signature(*, terms_reference: str, approval_token: Optional[str], accepted: PaymentRequirements) -> str:
    """Builds a PAYMENT-SIGNATURE header value — used by this backend's
    own live-verification/testing, and mirrored independently in
    buyer-agent's own copy of this file (no shared import).

    `accepted` is the PaymentRequirements the caller is choosing to pay
    with — a real x402 client echoes this back from whatever it received
    in PAYMENT-REQUIRED's `accepts[]`, per the spec's actual PaymentPayload
    shape (see schemas.py's PaymentPayload docstring for the conformance
    fix this closes).
    """
    model = PaymentPayload(
        accepted=accepted,
        payload=SchemeSpecificPayload(
            custodialReceipt=CustodialReceipt(terms_reference=terms_reference, approval_token=approval_token)
        ),
    )
    return _encode(model)


def parse_payment_signature(header_value: str) -> PaymentPayload:
    """Decodes a PAYMENT-SIGNATURE header value into a PaymentPayload.
    Raises MalformedPaymentHeaderError on bad base64/JSON, or
    pydantic.ValidationError if the decoded JSON doesn't match the
    expected shape — callers should catch both.
    """
    data = _decode_json(header_value)
    return PaymentPayload.model_validate(data)


def build_payment_response(
    *,
    success: bool,
    payer: Optional[str],
    transaction: str,
    amount_paise: Optional[int] = None,
    error_reason: Optional[str] = None,
    extensions: Optional[dict] = None,
) -> tuple[SettlementResponse, str]:
    """Builds the SettlementResponse object + its base64 header value for
    /pay's response — called on BOTH the success and failure paths that
    represent an actual settlement decision (see docs). `transaction`
    holds a Razorpay razorpay_order_id (never a payment_id — see
    schemas.py's SettlementResponse docstring); `reference` is set to the
    identical value.
    """
    model = SettlementResponse(
        success=success,
        errorReason=error_reason,
        payer=payer,
        transaction=transaction,
        reference=transaction,
        amount=str(amount_paise) if amount_paise is not None else None,
        extensions=extensions,
    )
    return model, _encode(model)
