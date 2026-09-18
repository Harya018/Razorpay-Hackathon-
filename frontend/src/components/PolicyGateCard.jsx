import { rupees, translateReason } from "../utils/eventTranslation.js";

// The single most important screen in this demo: makes the LLM/policy
// boundary visually explicit. Every field here is real data already
// returned by the backend —
//   catalogPrice   product.price (the backend's own catalog row)
//   requestedValue negotiation's proposed_offer.value (the LLM's proposal)
//   decision       "pending" | "approved" | "rejected" — from the real
//                  gate_decision audit event (policy-gate's actual
//                  /evaluate response), not a client-side guess
//   reason         policy-gate's real reason code (see evaluate.py)
//   maxAllowed     policy-gate's real max_allowed (paise, total) — the
//                  most the merchant would accept, only present on a
//                  rejection
// This component never computes or infers a decision itself — it only
// renders one that has already been made deterministically server-side.
export default function PolicyGateCard({ catalogPrice, requestedValue, decision = "pending", reason = null, maxAllowed = null }) {
  const discountPct =
    decision === "approved" && catalogPrice && requestedValue != null && catalogPrice > 0
      ? Math.round((1 - requestedValue / catalogPrice) * 100)
      : null;

  return (
    <div className="overflow-hidden rounded-lg border border-putty-dark bg-ivory">
      <div className="flex items-center justify-between border-b border-putty-dark bg-ivory-deep/60 px-3 py-2">
        <p className="font-body text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Policy Gate</p>
        <span className="font-body text-[10px] text-ink-soft/60">Deterministic authorization — not an LLM decision</span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 px-3 py-3 font-body text-xs">
        <div>
          <p className="text-ink-soft/60">Catalog price</p>
          <p className="font-semibold text-ink">{rupees(catalogPrice)}</p>
        </div>
        <div>
          <p className="text-ink-soft/60">Requested price</p>
          <p className="font-semibold text-ink">{requestedValue != null ? rupees(requestedValue) : "—"}</p>
        </div>
        {decision === "approved" && (
          <>
            <div>
              <p className="text-ink-soft/60">Discount</p>
              <p className="font-semibold text-moss-dark">{discountPct != null ? `${discountPct}%` : "—"}</p>
            </div>
            <div>
              <p className="text-ink-soft/60">Final authorized price</p>
              <p className="font-semibold text-moss-dark">{rupees(requestedValue)}</p>
            </div>
          </>
        )}
        {decision === "rejected" && maxAllowed != null && (
          <div className="col-span-2">
            <p className="text-ink-soft/60">Minimum allowed by policy</p>
            <p className="font-semibold text-ink">{rupees(maxAllowed)}</p>
          </div>
        )}
      </div>

      <div className="border-t border-putty-dark px-3 py-2.5">
        {decision === "pending" && (
          <p className="flex items-center gap-1.5 font-body text-xs font-medium text-ink-soft">
            <span className="h-2 w-2 animate-pulse rounded-full bg-putty-dark" /> Awaiting evaluation
          </p>
        )}
        {decision === "approved" && (
          <p className="flex items-center gap-1.5 font-body text-xs font-semibold text-moss-dark">
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-moss text-[10px] text-ivory">✓</span>
            APPROVED
          </p>
        )}
        {decision === "rejected" && (
          <div>
            <p className="flex items-center gap-1.5 font-body text-xs font-semibold text-rose-700">
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-rose-600 text-[10px] text-white">✕</span>
              REJECTED
            </p>
            {reason && <p className="mt-1 font-body text-[11px] text-rose-700/80">{translateReason(reason)}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
