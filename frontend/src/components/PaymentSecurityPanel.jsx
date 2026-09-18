import Card from "./Card.jsx";

const STAGES = [
  "Negotiated Price",
  "Policy Authorization",
  "Token Verification",
  "Razorpay Order",
  "Razorpay Checkout",
  "Payment",
  "Signature Verification",
  "Order Confirmed",
  "Audit Event",
];

// A compact, static overview of the payment security chain — the
// per-order, per-step REAL evidence for this lives in
// AuthorizationLifecyclePanel (same audit data, step-by-step with
// timestamps); this card exists to make the Razorpay boundary and Test
// Mode status impossible to miss on the Payments tab specifically.
export default function PaymentSecurityPanel() {
  return (
    <Card title="Payment Security">
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded-full bg-amber-100 px-2.5 py-1 font-body text-xs font-semibold text-amber-800">Razorpay — TEST MODE</span>
        <span className="font-body text-xs text-ink-soft/60">No real payment is ever processed by this deployment.</span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {STAGES.map((stage, i) => (
          <div key={stage} className="flex items-center gap-1.5">
            <span className="rounded-md border border-putty-dark bg-ivory px-2 py-1 font-body text-[11px] text-ink-soft">{stage}</span>
            {i < STAGES.length - 1 && <span className="text-ink-soft/40">→</span>}
          </div>
        ))}
      </div>

      <p className="mt-3 font-body text-xs text-ink-soft/70">
        Payment amount is created only after Policy Gate authorization is verified — the frontend never computes or sends
        an authoritative amount. See "Authorization Lifecycle" for a real, per-order, timestamped walk through this exact
        chain, and "Webhook Center" below for signature/deduplication evidence on the webhook path specifically.
      </p>
    </Card>
  );
}
