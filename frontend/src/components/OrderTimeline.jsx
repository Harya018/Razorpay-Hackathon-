import { fmtDate } from "./ui.jsx";

// Curated, customer-readable timeline built ONLY from the real events the
// backend returned for this order (order_detail.py). Future fulfillment
// steps are shown greyed as "pending" — they are the platform's own
// lifecycle (merchant-advanced, persisted, timestamped), not a courier.
const LABELS = {
  cart_assessed: ["Stock Verified", (p, s) => s],
  offer_proposed: ["Negotiation Offer Proposed", (p, s) => s],
  gate_call: ["Sent to Policy Gate", (p, s) => s],
  gate_decision: ["Policy Gate Decision", (p, s) => s],
  negotiation_closed: ["Offer Accepted", (p, s) => s],
  order_created: ["Order Created", (p, s) => s],
  order_confirmed_client_side: ["Payment Initiated", () => "Razorpay checkout completed"],
  payment_verified: ["Payment Verified", (p, s) => s],
  payment_failed: ["Payment Failed", () => "Razorpay reported a failed payment"],
  stock_deducted: ["Inventory Updated", (p, s) => s],
  stock_deduction_failed: ["Inventory Issue", (p, s) => s],
  order_status_updated: [null, (p, s) => s],
  checkout_token_rejected: ["Discount Not Applied", (p, s) => s],
  agent_payment_completed: ["Agent Payment", (p, s) => s],
};

export default function OrderTimeline({ events, fulfillmentStatus, fulfillmentSteps, fulfillmentLabels }) {
  const done = events
    .filter((e) => LABELS[e.event_type])
    .map((e) => {
      const [label, describe] = LABELS[e.event_type];
      const isStatus = e.event_type === "order_status_updated";
      return {
        key: e.id,
        label: isStatus ? e.summary : label,
        detail: isStatus ? null : describe(e.payload || {}, e.summary),
        ts: e.created_at,
        tone: e.event_type.includes("failed") || (e.event_type === "gate_decision" && e.summary.startsWith("REJECTED")) ? "error" : "ok",
      };
    });

  const reachedIdx = fulfillmentStatus ? fulfillmentSteps.indexOf(fulfillmentStatus) : -1;
  const pending = fulfillmentSteps.slice(reachedIdx + 1).map((s) => ({ key: `pending-${s}`, label: fulfillmentLabels[s], pending: true }));
  const all = [...done, ...pending];

  return (
    <ol className="space-y-0">
      {all.map((step, i) => (
        <li key={step.key} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                step.pending ? "bg-putty-light text-ink-soft/50" : step.tone === "error" ? "bg-rose-600 text-white" : "bg-moss text-ivory"
              }`}
            >
              {step.pending ? "→" : step.tone === "error" ? "✕" : "✓"}
            </span>
            {i < all.length - 1 && <span className={`w-px flex-1 ${step.pending ? "bg-putty" : "bg-moss-light"}`} style={{ minHeight: "1.5rem" }} />}
          </div>
          <div className="min-w-0 flex-1 pb-3">
            <p className={`font-body text-sm font-medium ${step.pending ? "text-ink-soft/50" : "text-ink"}`}>{step.label}</p>
            {step.pending ? (
              <p className="font-body text-[11px] text-ink-soft/40">Pending</p>
            ) : (
              <p className="font-body text-[11px] text-ink-soft/70">
                {fmtDate(step.ts)}
                {step.detail && <span className="text-ink-soft/50"> — {step.detail}</span>}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
