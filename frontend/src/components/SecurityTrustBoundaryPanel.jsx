import Card from "./Card.jsx";

// Section 18's "Security & Trust Boundary" panel — a static architecture
// diagram, deliberately not fetched from an API: it describes what this
// system's code always does (LLMs propose, Policy Gate decides), not a
// per-request measurement. Every checklist line below names an actual
// mechanism implemented elsewhere in this codebase (linked in the
// comments) — nothing here is aspirational copy.
const STAGES = [
  { label: "LLM", desc: "Negotiates", detail: "Seller/buyer agents (LangGraph) — proposes offers only" },
  { label: "Policy Gate", desc: "Deterministic authorization", detail: "policy-gate service — independent DB, no LLM in the decision path" },
  { label: "Approval Token", desc: "Single-use authorization", detail: "Minted only on approval, redeemed exactly once" },
  { label: "Razorpay", desc: "Payment", detail: "Test Mode — amount comes from the redeemed token, never the client" },
];

const CHECKLIST = [
  "Policy Gate independently re-verifies the catalog price on every /evaluate call — a caller's claimed price is never trusted (policy-gate/app/routes/evaluate.py)",
  "The backend cannot directly authorize a discount — only policy-gate can mint an approval token",
  "Approval tokens are cryptographically verified before payment, via a live /verify call to policy-gate",
  "Approval tokens are single-use, enforced by an atomic DB update — a replayed token is rejected, not silently reused",
  "The Razorpay payment amount is read from the redeemed token's terms, never from any client-supplied amount",
  "Every negotiation, gate decision, and payment event is written to a hash-chained audit log — tampering with one entry breaks the chain",
];

export default function SecurityTrustBoundaryPanel() {
  return (
    <Card title="Security &amp; Trust Boundary" note="LLMs negotiate; deterministic code decides whether money can move.">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch sm:gap-0">
        {STAGES.map((stage, i) => (
          <div key={stage.label} className="flex flex-1 items-center">
            <div className="flex-1 rounded-lg border border-putty-dark bg-ivory p-3 text-center">
              <p className="font-display text-sm font-semibold text-ink">{stage.label}</p>
              <p className="mt-0.5 font-body text-xs font-medium text-clay">{stage.desc}</p>
              <p className="mt-1 font-body text-[10px] leading-snug text-ink-soft/60">{stage.detail}</p>
            </div>
            {i < STAGES.length - 1 && (
              <span className="hidden shrink-0 px-1.5 font-body text-lg text-ink-soft/40 sm:block" aria-hidden="true">→</span>
            )}
          </div>
        ))}
      </div>

      <ul className="mt-4 space-y-1.5">
        {CHECKLIST.map((line) => (
          <li key={line} className="flex items-start gap-2 font-body text-xs text-ink-soft">
            <span className="mt-0.5 shrink-0 font-semibold text-moss-dark" aria-hidden="true">✓</span>
            {line}
          </li>
        ))}
      </ul>
    </Card>
  );
}
