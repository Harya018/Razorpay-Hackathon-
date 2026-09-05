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
export async function startCheckout({ product, quantity = 1, approvalToken = null, sessionId = null, onStatus, onClose }) {
  const res = await fetch(`${API_BASE_URL}/order/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

  const { razorpay_order_id, amount, key_id } = await res.json();

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
        onStatus?.(confirmRes.ok ? "Payment successful" : "Payment made, but confirmation failed — contact support");
      } catch {
        onStatus?.("Payment made, but confirmation failed — contact support");
      }
      onClose?.(true);
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
