"""HTTP client for the seller's /agent/v1/* interface.

Built ONLY from docs/agent-commerce-interface.md (plus its curl-session
and OpenAPI companion files) — this file does not import anything from
the seller's backend, and none of its request/response shapes were
copied from backend source. If a shape here turns out to be wrong, the
fix is to re-read the doc, not to go peek at the seller's code.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

from app.config import settings
from app.x402_headers import (
    MalformedPaymentHeaderError,
    build_payment_signature,
    parse_payment_required,
    parse_payment_response,
)

logger = logging.getLogger(__name__)


class SellerAPIError(RuntimeError):
    """Raised for any non-2xx/402 response the client doesn't know how to
    interpret as a normal outcome (auth failures, validation errors,
    not-found, etc.) — carries the status code and body for the caller
    to decide what to do.
    """

    def __init__(self, status_code: int, body, payment_response: Optional[dict] = None):
        self.status_code = status_code
        self.body = body
        self.payment_response = payment_response
        super().__init__(f"Seller API returned {status_code}: {body}")


@dataclass
class CatalogItem:
    id: int
    name: str
    description: Optional[str]
    price: int  # paise
    currency: str
    stock: int
    negotiable: bool


@dataclass
class NegotiateResult:
    approved: bool
    approval_token: Optional[str]
    final_terms: Optional[dict]
    reason: Optional[str]
    max_allowed: Optional[int]
    # Phase 11 — the seller agent's natural-language chat reply, if it sent
    # one. Purely presentational: never used for any decision in this
    # client, which still only ever looks at approved/final_terms/
    # max_allowed.
    message: Optional[str] = None


@dataclass
class PurchaseTerms:
    amount: int
    currency: str
    accepted_payment_methods: list
    payment_endpoint: str
    terms_reference: str
    # x402 V2 wire-format layer (Phase 8) — decoded PAYMENT-REQUIRED
    # header, when the seller sent one and it decoded cleanly. None if
    # absent or malformed; the JSON body fields above remain this client's
    # actual source of truth regardless.
    payment_required: Optional[dict] = None


@dataclass
class PayResult:
    order_id: int
    razorpay_order_id: str
    status: str
    amount: int
    # x402 V2 wire-format layer (Phase 8) — decoded PAYMENT-RESPONSE
    # header. `transaction` inside it is a Razorpay order id, NOT a
    # blockchain transaction hash — see docs/agent-commerce-interface.md.
    payment_response: Optional[dict] = None


class SellerClient:
    def __init__(self, base_url: str, buyer_agent_id: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.buyer_agent_id = buyer_agent_id
        self.api_key = api_key

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def register(self, buyer_agent_id: str, display_name: Optional[str] = None) -> dict:
        resp = requests.post(
            f"{self.base_url}/agent/v1/register",
            json={"buyer_agent_id": buyer_agent_id, "display_name": display_name},
            timeout=10,
        )
        if resp.status_code != 201:
            raise SellerAPIError(resp.status_code, resp.json())
        return resp.json()

    def get_catalog(self) -> list[CatalogItem]:
        resp = requests.get(f"{self.base_url}/agent/v1/catalog", timeout=10)
        if resp.status_code != 200:
            raise SellerAPIError(resp.status_code, resp.json())
        return [
            CatalogItem(
                id=item["id"],
                name=item["name"],
                description=item.get("description"),
                price=item["price"],
                currency=item["currency"],
                stock=item["stock"],
                negotiable=item["negotiable"],
            )
            for item in resp.json()
        ]

    def negotiate(
        self,
        product_id: int,
        quantity: int,
        proposed_type: str,
        proposed_value: int,
        message: Optional[str] = None,
    ) -> NegotiateResult:
        body_json = {
            "product_id": product_id,
            "quantity": quantity,
            "buyer_agent_id": self.buyer_agent_id,
            "proposed_terms": {"type": proposed_type, "value": proposed_value},
        }
        # Phase 11 — optional free-text chat message, e.g. "Hi, I'm
        # interested in the Hand-Painted Ceramic Table Vase. My budget is ₹2000." Used
        # only so the seller's reply reads like an actual conversation;
        # never affects proposed_terms above.
        if message is not None:
            body_json["message"] = message

        resp = requests.post(
            f"{self.base_url}/agent/v1/negotiate",
            headers=self._auth_headers(),
            json=body_json,
            timeout=15,
        )
        if resp.status_code != 200:
            raise SellerAPIError(resp.status_code, resp.json())
        body = resp.json()
        return NegotiateResult(
            approved=body["approved"],
            approval_token=body.get("approval_token"),
            final_terms=body.get("final_terms"),
            reason=body.get("reason"),
            max_allowed=body.get("max_allowed"),
            message=body.get("message"),
        )

    def purchase(self, product_id: int, quantity: int, approval_token: Optional[str] = None) -> PurchaseTerms:
        resp = requests.post(
            f"{self.base_url}/agent/v1/purchase",
            headers=self._auth_headers(),
            json={
                "product_id": product_id,
                "quantity": quantity,
                "buyer_agent_id": self.buyer_agent_id,
                "approval_token": approval_token,
            },
            timeout=15,
        )
        # Per the doc, /purchase ALWAYS responds 402 on success — that IS
        # the expected outcome here, not an error.
        if resp.status_code != 402:
            raise SellerAPIError(resp.status_code, resp.json())
        body = resp.json()

        payment_required = None
        header_value = resp.headers.get("PAYMENT-REQUIRED")
        if header_value:
            try:
                payment_required = parse_payment_required(header_value)
            except MalformedPaymentHeaderError as e:
                # Additive layer — a malformed/missing header never blocks
                # the purchase flow, which runs on the JSON body regardless.
                logger.warning("PAYMENT-REQUIRED header present but malformed: %s", e)

        return PurchaseTerms(
            amount=body["amount"],
            currency=body["currency"],
            accepted_payment_methods=body["accepted_payment_methods"],
            payment_endpoint=body["payment_endpoint"],
            terms_reference=body["terms_reference"],
            payment_required=payment_required,
        )

    def pay(self, terms_reference: str, approval_token: Optional[str] = None, accepted: Optional[dict] = None) -> PayResult:
        headers = self._auth_headers()
        # x402 V2 wire-format layer — additive alongside the JSON body
        # below, which remains this client's actual source of truth.
        # `accepted` should be the PaymentRequirements this client
        # received via PAYMENT-REQUIRED on the preceding /purchase call
        # (payment_required["accepts"][0], see purchase() below) — a
        # conformance fix, see x402_headers.py's build_payment_signature
        # docstring. Falls back to an empty dict if the caller never
        # captured one (e.g. the seller sent no PAYMENT-REQUIRED header at
        # all) rather than crashing — the JSON body remains this client's
        # actual source of truth regardless of what this header carries.
        headers["PAYMENT-SIGNATURE"] = build_payment_signature(
            terms_reference=terms_reference, approval_token=approval_token, accepted=accepted or {}
        )

        resp = requests.post(
            f"{self.base_url}/agent/v1/pay",
            headers=headers,
            json={
                "terms_reference": terms_reference,
                "approval_token": approval_token,
                "buyer_agent_id": self.buyer_agent_id,
            },
            timeout=15,
        )

        payment_response = None
        header_value = resp.headers.get("PAYMENT-RESPONSE")
        if header_value:
            try:
                payment_response = parse_payment_response(header_value)
            except MalformedPaymentHeaderError as e:
                logger.warning("PAYMENT-RESPONSE header present but malformed: %s", e)

        if resp.status_code != 200:
            # Per the doc, PAYMENT-RESPONSE is attached on this failure
            # path too (unknown/used terms_reference) — surfaced here
            # rather than silently dropped, since that's exactly the known
            # bug class the v2 spec calls out.
            raise SellerAPIError(resp.status_code, resp.json(), payment_response=payment_response)
        body = resp.json()

        return PayResult(
            order_id=body["order_id"],
            razorpay_order_id=body["razorpay_order_id"],
            status=body["status"],
            amount=body["amount"],
            payment_response=payment_response,
        )

    def order_status(self, order_id: int) -> dict:
        resp = requests.get(f"{self.base_url}/agent/v1/order/{order_id}/status", timeout=10)
        if resp.status_code != 200:
            raise SellerAPIError(resp.status_code, resp.json())
        return resp.json()


def client_from_settings() -> SellerClient:
    return SellerClient(settings.SELLER_BASE_URL, settings.BUYER_AGENT_ID, settings.BUYER_API_KEY)
