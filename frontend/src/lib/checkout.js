import { toastError, toastSuccess } from "./toast.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Shared by the plain "Buy" flow and the negotiation handoff — both end the
// same way: create a Razorpay order, then open the hosted checkout widget.
// approvalToken (from a gate-approved negotiation) is the ONLY way a
// discount reaches checkout — the backend independently verifies it
// against the policy-gate before applying anything; omit it for the
// normal, un-negotiated purchase path.
// onClose (Phase 9, optional) fires once the Razorpay modal actually
// closes — whether via a completed payment or the user dismissing it —
// so a multi-item cart checkout can sequence through orders one at a
// time instead of opening several payment modals at once. It receives
// one argument, `paid` (true/false), so a caller like Cart.jsx's
// checkout-all loop can tell a completed payment apart from a cancelled
// one instead of treating both as "done with this item."
// sessionId (optional): the negotiation session that earned approvalToken,
// if any — sent so the backend/policy-gate can confirm this token is
// actually being redeemed for the negotiation that produced it, closing a
// red-team-confirmed gap where any approval_token could be redeemed
// against an unrelated checkout for the same product/quantity.
// expectedAmount (optional, paise): what the CALLER believes the
// negotiated total is. The backend never trusts this — it's only used
// here, client-side, to compare against the real `amount` /order/create
// returns. If a token silently failed re-verification (already used,
// expired terms, session mismatch — see payments.py's
// create_order_with_optional_discount), the backend falls through to the
// full listed price rather than erroring, so this is the only way the
// UI can tell the shopper "the discount didn't apply" before they pay.
// onAuthorizationInvalid (optional): fired in exactly that case, so a
// caller like Cart.jsx can clear its own stale negotiated-price state.
export async function startCheckout({
  product,
  quantity = 1,
  approvalToken = null,
  sessionId = null,
  expectedAmount = null,
  onStatus,
  onClose,
  onAuthorizationInvalid,
}) {
  // Phase 4 (idempotency): one key per checkout attempt — the backend
  // stores it on the Order row and returns the SAME order for a repeated
  // request carrying it, rather than creating a second real Razorpay
  // order. Defense-in-depth alongside the UI-level double-click guards
  // already in Cart.jsx/ProductDetail.jsx (checkingOut state).
  const idempotencyKey = crypto.randomUUID();
  const res = await fetch(`${API_BASE_URL}/order/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      product_id: product.id,
      quantity,
      ...(approvalToken ? { approval_token: approvalToken } : {}),
      ...(approvalToken && sessionId ? { session_id: sessionId } : {}),
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to create order");
  }

  const { razorpay_order_id, amount, key_id, order_id } = await res.json();

  if (expectedAmount != null && amount !== expectedAmount) {
    const msg = "The negotiated authorization is no longer valid — you're being charged the full listed price instead.";
    onStatus?.(msg);
    toastError(msg);
    onAuthorizationInvalid?.();
  }

  const razorpay = new window.Razorpay({
    key: key_id,
    amount,
    currency: "INR",
    order_id: razorpay_order_id,
    name: product.name,
    description: product.description || "",
    // Phase 18.6: this used to just say "Payment initiated" and stop —
    // this backend had NO path from a completed payment to a "paid"
    // order status other than a real Razorpay webhook, which needs a
    // public tunnel this project has never had running locally. Every
    // "paid" order in this project's history turned out to be a redteam
    // test script simulating a webhook call, not a real payment. Now
    // confirms immediately via the checkout response's own signature,
    // independently verified server-side — never trusted from the
    // client alone — so the dashboard reflects a real payment right away
    // even with no webhook tunnel running.
    handler: async (response) => {
      onStatus?.("Payment successful — confirming...");
      try {
        const confirmRes = await fetch(`${API_BASE_URL}/order/confirm`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          }),
        });
        if (confirmRes.ok) {
          onStatus?.("Payment successful");
          toastSuccess(`Payment verified — ₹${(amount / 100).toFixed(2)} paid.`);
          // Only after the BACKEND said the signature verified — never on
          // Razorpay's client callback alone.
          onClose?.(true, order_id);
          return;
        }
        onStatus?.("Payment made, but confirmation failed — contact support");
        toastError("Payment made, but signature verification failed — contact support.");
      } catch {
        onStatus?.("Payment made, but confirmation failed — contact support");
        toastError("Payment made, but confirmation failed — contact support.");
      }
      onClose?.(true, null);
    },
    modal: {
      ondismiss: () => {
        onStatus?.("Payment cancelled");
        onClose?.(false);
      },
    },
  });

  razorpay.open();
}
