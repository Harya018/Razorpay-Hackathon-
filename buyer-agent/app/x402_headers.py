"""Pure encode/decode helpers for x402 V2's three headers, built strictly
from docs/agent-commerce-interface.md's "x402 V2 Conformance and Its
Limits" section (plus the real x402 V2 spec it links to) — not by
importing anything from the seller's backend. Same independence rule
Phase 4b's client.py already follows for the JSON-body flow.

This client treats decoded headers as plain dicts rather than a strict
schema — the JSON-body flow (client.py) remains this agent's actual
source of truth; header values are read/constructed alongside it, never
instead of it, per the doc's explicit backward-compatibility note.
"""

import base64
import json
from typing import Optional


class MalformedPaymentHeaderError(ValueError):
    pass


def decode_header(header_value: str) -> dict:
    try:
        raw = base64.b64decode(header_value, validate=True)
    except Exception as e:
        raise MalformedPaymentHeaderError(f"header value is not valid base64: {e}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise MalformedPaymentHeaderError(f"decoded header value is not valid JSON: {e}") from e


def encode_header(obj: dict) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def parse_payment_required(header_value: str) -> dict:
    """Decodes a PAYMENT-REQUIRED header into its PaymentRequired dict.
    Per the doc, the field this client actually needs out of it is
    accepts[0].extra.terms_reference (it already has amount/terms_reference
    from the JSON body too — this is read for wire-format conformance, and
    cross-checked against the JSON body rather than trusted alone).
    """
    return decode_header(header_value)


def build_payment_signature(*, terms_reference: str, approval_token: Optional[str], accepted: dict) -> str:
    """Builds the PAYMENT-SIGNATURE header value for /pay. Per the doc,
    this system substitutes payload.custodialReceipt {terms_reference,
    approval_token} for x402's real signature/authorization fields — there
    is no cryptographic signature anywhere in this client. This header is
    REQUIRED by the seller (a missing/malformed value gets a 400).

    Conformance fix (re-verified live against the real x402 V2 spec, not
    recalled — see docs/x402-conformance-diff.md): PaymentPayload does
    NOT carry flattened top-level scheme/network fields — it carries
    `accepted`, the FULL PaymentRequirements object being paid with,
    normally echoed back from whatever the server offered. `accepted`
    here should be `payment_required["accepts"][0]` as decoded from the
    seller's own PAYMENT-REQUIRED header on the preceding /purchase
    response (see client.py's purchase()/pay()) — never reconstructed
    from scratch, since only the seller knows the real payTo/extra values.
    """
    payload = {
        "x402Version": 2,
        "accepted": accepted,
        "payload": {"custodialReceipt": {"terms_reference": terms_reference, "approval_token": approval_token}},
    }
    return encode_header(payload)


def parse_payment_response(header_value: str) -> dict:
    """Decodes a PAYMENT-RESPONSE header into its SettlementResponse dict.
    Per the doc, `transaction` here is a Razorpay order id, not a
    blockchain transaction hash — this client must not treat it as one.
    """
    return decode_header(header_value)
