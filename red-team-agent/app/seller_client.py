"""Thin, deliberately low-level HTTP wrappers around the seller's public
interfaces (docs/agent-commerce-interface.md for /agent/v1/*, plus the
human /negotiate/* routes that back the merchant dashboard's "Human
Negotiations" panel). Unlike buyer-agent's client.py, attacks here want
the raw requests.Response (status code, headers, body) rather than a
validated dataclass — the whole point is to see what the server actually
does with malformed/adversarial/concurrent input, not to assume it
matches the happy-path shape.
"""

import base64
import json
from typing import Optional

import requests

from app.config import settings


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def build_payment_signature_header(
    terms_reference: str, approval_token: Optional[str], accepted: Optional[dict] = None
) -> str:
    """/agent/v1/pay REQUIRES a PAYMENT-SIGNATURE header (see
    docs/x402-v2-conformance.md). Re-derived here from the public docs
    alone, independently of backend/buyer-agent's own copies of this same
    shape — same 'read the public contract, don't import the
    implementation' rule this whole client already follows.

    Conformance fix (docs/x402-conformance-diff.md): PaymentPayload
    carries `accepted` (the FULL PaymentRequirements object), not
    flattened top-level scheme/network fields. `accepted` defaults to a
    schema-valid PLACEHOLDER when the caller doesn't have the real one
    handy — deliberate, since this harness's tests exercise the
    approval_token/terms_reference matching logic and concurrency/replay
    properties, not exact field-echoing fidelity; unlike buyer-agent's
    production client, which always echoes the seller's real
    PAYMENT-REQUIRED accepts[0] verbatim (see buyer-agent/app/
    x402_headers.py). Pass a real `accepted` dict explicitly for any test
    that specifically cares about it matching.
    """
    accepted = accepted or {
        "scheme": "exact",
        "network": "inr-fiat:razorpay-test",
        "amount": "0",
        "asset": "INR",
        "payTo": "unknown",
        "maxTimeoutSeconds": 300,
    }
    payload = {
        "x402Version": 2,
        "accepted": accepted,
        "payload": {"custodialReceipt": {"terms_reference": terms_reference, "approval_token": approval_token}},
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


# --- /agent/v1/* -----------------------------------------------------------


def negotiate(buyer_id: str, api_key: str, product_id: int, quantity: int, offer_type: str, value) -> requests.Response:
    return requests.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/negotiate",
        headers=auth_headers(api_key),
        json={
            "product_id": product_id,
            "quantity": quantity,
            "buyer_agent_id": buyer_id,
            "proposed_terms": {"type": offer_type, "value": value},
        },
        timeout=15,
    )


def negotiate_raw(buyer_id: str, api_key: str, body: dict) -> requests.Response:
    """For malformed_terms.py — sends whatever body dict it's given,
    unvalidated, so tests can send wrong types / extra fields / missing
    fields freely.
    """
    return requests.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/negotiate",
        headers=auth_headers(api_key),
        json=body,
        timeout=15,
    )


def purchase(buyer_id: str, api_key: str, product_id: int, quantity: int, approval_token: Optional[str] = None) -> requests.Response:
    return requests.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/purchase",
        headers=auth_headers(api_key),
        json={
            "product_id": product_id,
            "quantity": quantity,
            "buyer_agent_id": buyer_id,
            "approval_token": approval_token,
        },
        timeout=15,
    )


def pay(buyer_id: str, api_key: str, terms_reference: str, approval_token: Optional[str] = None) -> requests.Response:
    headers = auth_headers(api_key)
    headers["PAYMENT-SIGNATURE"] = build_payment_signature_header(terms_reference, approval_token)
    return requests.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/pay",
        headers=headers,
        json={
            "terms_reference": terms_reference,
            "approval_token": approval_token,
            "buyer_agent_id": buyer_id,
        },
        timeout=15,
    )


def pay_raw(buyer_id: str, api_key: str, terms_reference: str, approval_token: Optional[str], payment_signature_header: Optional[str]) -> requests.Response:
    """For tampering/trust-boundary attacks that need to deliberately omit
    or corrupt PAYMENT-SIGNATURE — pass None to omit the header entirely,
    or any string to send it verbatim (malformed or otherwise).
    """
    headers = auth_headers(api_key)
    if payment_signature_header is not None:
        headers["PAYMENT-SIGNATURE"] = payment_signature_header
    return requests.post(
        f"{settings.SELLER_BASE_URL}/agent/v1/pay",
        headers=headers,
        json={
            "terms_reference": terms_reference,
            "approval_token": approval_token,
            "buyer_agent_id": buyer_id,
        },
        timeout=15,
    )


def order_status(order_id: int) -> requests.Response:
    return requests.get(f"{settings.SELLER_BASE_URL}/agent/v1/order/{order_id}/status", timeout=10)


def catalog() -> requests.Response:
    return requests.get(f"{settings.SELLER_BASE_URL}/agent/v1/catalog", timeout=10)


def negotiate_and_get_token(buyer_id: str, api_key: str, product_id: int, quantity: int, value: int) -> dict:
    """Convenience helper for attacks that need a genuinely valid,
    gate-approved token as a starting point (e.g. to then attack the
    /pay step). Raises if negotiation isn't approved.
    """
    resp = negotiate(buyer_id, api_key, product_id, quantity, "discount", value)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("approved"):
        raise RuntimeError(f"negotiate_and_get_token: offer not approved: {body}")
    return body


# --- Human checkout (/order/create, /webhook/razorpay) ---------------------


def order_create(product_id: int, quantity: int, approval_token: Optional[str] = None) -> requests.Response:
    return requests.post(
        f"{settings.BACKEND_BASE_URL}/order/create",
        json={"product_id": product_id, "quantity": quantity, "approval_token": approval_token},
        timeout=15,
    )


def razorpay_webhook_raw(body_bytes: bytes, signature: str) -> requests.Response:
    """Sends a raw webhook POST with a caller-supplied body and signature —
    used by webhook_replay.py to send the exact same bytes+signature more
    than once (a real replay), and to test tampering (a signature that
    doesn't match the body).
    """
    return requests.post(
        f"{settings.BACKEND_BASE_URL}/webhook/razorpay",
        data=body_bytes,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
        timeout=15,
    )


# --- Human negotiation (/negotiate/*) ---------------------------------------


def negotiate_start(product_id: int, cart_quantity: int = 1) -> requests.Response:
    # Each call runs 1-2 LLM round-trips server-side (decide_to_offer,
    # propose_offer); under Groq daily-quota exhaustion this falls back to
    # Gemini's own 4.5s-paced rate limiter, which can push real latency
    # well past a 15-30s budget under back-to-back red-team traffic — a
    # timeout here is this client giving up too early, not the server
    # actually failing.
    return requests.post(
        f"{settings.BACKEND_BASE_URL}/negotiate/start",
        json={"product_id": product_id, "cart_quantity": cart_quantity},
        timeout=90,
    )


def negotiate_message(session_id: str, user_message: str) -> requests.Response:
    return requests.post(
        f"{settings.BACKEND_BASE_URL}/negotiate/message",
        json={"session_id": session_id, "user_message": user_message},
        timeout=90,
    )


def negotiate_audit(session_id: str) -> requests.Response:
    # A plain DB read with no LLM call, but FastAPI's sync-route
    # threadpool is shared with negotiate_start/negotiate_message's much
    # slower LLM-bound calls — under back-to-back red-team traffic this
    # can queue behind them, not because this read is itself slow.
    return requests.get(f"{settings.BACKEND_BASE_URL}/negotiate/{session_id}/audit", timeout=60)
