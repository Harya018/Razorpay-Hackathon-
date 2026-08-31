from pydantic import BaseModel, Field


class OrderCreateRequest(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    # Phase 3: the ONLY way a discount can reach checkout. No raw amount is
    # ever accepted from the client — this token is independently verified
    # against the policy-gate's own record before it changes anything. A
    # missing or invalid token means the full listed price is charged,
    # never a silent fallback to whatever the client claims.
    approval_token: str | None = None
    # Optional — the human negotiation session_id that earned
    # approval_token, if any. Red-team-confirmed gap (redteam's
    # tampering.py, "session_id_substitution"): without this, an
    # approval_token from ANY session could be redeemed against any other
    # checkout for the same product_id/quantity. When omitted, behavior
    # is unchanged (backward compatible); when present, it's checked
    # against the token's own recorded session in policy-gate's /verify.
    session_id: str | None = None


class OrderCreateResponse(BaseModel):
    razorpay_order_id: str
    amount: int
    key_id: str


class OrderConfirmRequest(BaseModel):
    """The three fields Razorpay's checkout.js hands to the client-side
    `handler` callback on a successful payment. Phase 18.6 — this backend
    previously had NO path from a completed payment to `status = "paid"`
    other than a real Razorpay webhook delivery, which requires a public
    tunnel (ngrok) that isn't running in local/demo deployments. Verified
    server-side (HMAC via razorpay_client.utility.verify_payment_signature,
    the same mechanism the webhook path uses) — never trusted from the
    client alone, consistent with this project's own rule that no raw
    claim from a caller changes money-affecting state without independent
    verification.
    """

    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
