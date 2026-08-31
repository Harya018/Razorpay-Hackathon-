"""x402 V2 wire-format objects — PaymentRequired, PaymentPayload,
SettlementResponse — field names and shapes taken from
https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md
and https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md
(re-read live for Phase 11, not recalled from memory — this caught a real
discrepancy between an example in the Phase 11 brief and the actual spec
text; see docs/x402-v2-conformance.md's "A correction made during this
phase" section for exactly what and why).

This system settles in INR via Razorpay test-mode, not on-chain — several
fields keep the real spec's SHAPE but had their MEANING substituted for a
fiat merchant. Every substitution is documented in
docs/x402-v2-conformance.md, which is the current authoritative reference
(docs/agent-commerce-interface.md's own x402 section is Phase 8's
original pass and is now superseded on field VALUES, not on the honesty
argument, which still holds).
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

X402_VERSION = 2

# "exact" is the real x402 scheme name — it describes settling the exact
# quoted amount (no partial/streaming payment), which genuinely applies
# here. What does NOT apply (a signed EIP-3009 authorization) is handled
# by substituting payload.custodialReceipt for signature/authorization,
# not by hiding behind a non-registry scheme name.
SCHEME = "exact"

# CAIP-2-SHAPED (namespace:reference) but deliberately NOT a registered
# CAIP-2 namespace — "inr-fiat:" cannot be confused with "eip155:" or
# "solana:". This is x402 V2's own documented Extensions mechanism, not
# an undocumented side channel. See EXTENSION_DISCLAIMER below — this
# exact sentence must appear, verbatim, in the discovery endpoint, the
# OpenAPI spec description, and docs/x402-v2-conformance.md.
NETWORK = "inr-fiat:razorpay-test"
ASSET = "INR"  # the spec's own ISO 4217 fallback for `asset` — a direct fit
SETTLEMENT_TYPE = "fiat-custodial"
FACILITATOR = "razorpay-test-mode"

EXTENSION_DISCLAIMER = (
    "Settlement is processed via Razorpay (India, fiat, test-mode). This is not an "
    "onchain settlement network. network values under the inr-fiat: prefix are a "
    "documented x402 extension for this deployment, not part of the core x402 "
    "network registry."
)


class ResourceInfo(BaseModel):
    """Top-level on PaymentRequired — NOT nested inside each
    PaymentRequirements entry. The Phase 11 brief's example nested
    `resource`/`description` inside `accepts[]`; the real spec (section
    5.1.2, re-checked live) keeps them here instead. See
    docs/x402-v2-conformance.md.
    """

    url: str
    description: Optional[str] = None
    mimeType: str = "application/json"


class PaymentRequirements(BaseModel):
    scheme: Literal["exact"] = SCHEME
    network: Literal["inr-fiat:razorpay-test"] = NETWORK
    amount: str  # paise, as a string — the spec's actual field name (not "maxAmountRequired")
    asset: Literal["INR"] = ASSET
    payTo: str  # Razorpay PUBLIC key id — not a wallet address, not a secret
    maxTimeoutSeconds: int = 300  # shape-conformant only; not enforced, see docs
    extra: Optional[dict] = None


class ExtensionsBlock(BaseModel):
    """x402 V2's own formal Extensions mechanism (re-verified live against
    the spec for the conformance pass — see docs/x402-conformance-diff.md):
    'Servers advertise supported extensions in PaymentRequired, and
    clients echo them in PaymentPayload.' `info` is extension-specific
    data; `schema` is a JSON Schema describing `info`'s shape. Previously
    this codebase only carried the inr-fiat: disclaimer informally
    (network-namespace prefix + a discovery-endpoint string) without ever
    populating this formal object — that was a real conformance gap,
    closed here: the SAME disclaimer now also appears as spec-shaped
    Extensions data, not just prose.
    """

    model_config = ConfigDict(populate_by_name=True)

    info: dict
    # Named schema_ in Python (schema shadows a deprecated BaseModel
    # attribute in Pydantic v2) but serialized/accepted on the wire as
    # "schema", the spec's actual field name.
    schema_: dict = Field(alias="schema")


class PaymentRequired(BaseModel):
    """Encoded into the PAYMENT-REQUIRED header on /purchase's 402."""

    x402Version: int = X402_VERSION
    error: Optional[str] = None
    resource: ResourceInfo
    accepts: list[PaymentRequirements]
    extensions: Optional[ExtensionsBlock] = None


class CustodialReceipt(BaseModel):
    """This system's substitute for x402's `signature` + `authorization`
    fields on the "exact" EVM scheme. There is no cryptographic signature
    here — `approval_token` (the policy-gate's single-use, buyer-bound
    approval) plays the equivalent role: proof that this specific charge
    was authorized, independently verified server-side, never merely
    claimed by the client. Named `custodialReceipt`, not `signature`, so
    nothing implies cryptographic proof that doesn't exist.
    """

    terms_reference: str
    approval_token: Optional[str] = None


class SchemeSpecificPayload(BaseModel):
    custodialReceipt: CustodialReceipt


class PaymentPayload(BaseModel):
    """Decoded from the PAYMENT-SIGNATURE header on /pay's request. This
    header is REQUIRED as of Phase 11 (Phase 8 made it optional) — see
    docs/x402-v2-conformance.md's "Backward compatibility decision".

    Conformance fix (docs/x402-conformance-diff.md): the real spec's
    PaymentPayload does NOT carry flattened top-level `scheme`/`network`
    fields — it carries `accepted`, the FULL PaymentRequirements object
    the client is choosing to pay with (normally echoed back verbatim
    from whatever the server offered in PAYMENT-REQUIRED's `accepts[]`).
    The previous implementation had invented a flattened shape that
    resembled but didn't match the spec; every client in this system
    (buyer-agent, red-team-agent, redteam) has been updated to decode
    PAYMENT-REQUIRED and echo its `accepts[0]` back as `accepted`.
    """

    x402Version: int = X402_VERSION
    resource: Optional[ResourceInfo] = None
    accepted: PaymentRequirements
    payload: SchemeSpecificPayload
    extensions: Optional[dict] = None


class SettlementResponse(BaseModel):
    """Encoded into the PAYMENT-RESPONSE header on /pay's response — on
    BOTH success and failure, per the v2 spec's explicit callout that
    omitting this header on failure is a known bug class.
    """

    success: bool
    settlementType: Literal["fiat-custodial"] = SETTLEMENT_TYPE
    errorReason: Optional[str] = None
    payer: Optional[str] = None  # buyer_agent_id — this system's identity, not a wallet address
    # `transaction` is the real spec's field name (verified live against
    # the spec text); `reference` is the name the Phase 11 brief asked
    # for — both present, identical value, so either name works for a
    # consuming client, but `transaction` is what a strict spec check
    # looks for. BOTH hold a Razorpay razorpay_order_id, never a
    # razorpay_payment_id ("pay_..." string) — payment capture is
    # asynchronous, happening later via Razorpay's webhook, so no
    # payment_id exists yet at the moment this header is built. See
    # docs/x402-v2-conformance.md.
    transaction: str
    reference: str
    network: Literal["inr-fiat:razorpay-test"] = NETWORK
    amount: Optional[str] = None  # paise, as a string
    extensions: Optional[dict] = None


class DiscoveryResponse(BaseModel):
    """GET /agent/v1/discovery — new in Phase 11. No authentication
    required, mirrors GET /agent/v1/catalog's openness. A real x402 V2
    client fetches this BEFORE transacting to learn what this catalog
    accepts, without needing to already know this merchant's docs.
    """

    x402Version: int = X402_VERSION
    supportedSchemes: list[str] = [SCHEME]
    supportedNetworks: list[str] = [NETWORK]
    extensionDisclaimer: str = EXTENSION_DISCLAIMER
    catalogUrl: str = "/agent/v1/catalog"
    negotiateUrl: str = "/agent/v1/negotiate"
    purchaseUrl: str = "/agent/v1/purchase"
    payUrl: str = "/agent/v1/pay"
