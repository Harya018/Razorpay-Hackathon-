import Card from "./Card.jsx";

// Real evidence (redteam/results/tampering_results.json's
// tampering.direct_discount_injection entry) that policy-gate never
// trusts a caller's claimed price/discount — it independently re-fetches
// the real catalog price and computes the allowed floor itself. `attack`
// is passed in from the Security page's single /dashboard/security-posture
// fetch.
export default function PriceReVerificationCard({ attack }) {
  return (
    <Card title="Price &amp; Discount Integrity" note="What happens when a caller tries to dictate the price instead of negotiating it.">
      <div className="grid grid-cols-1 gap-0 overflow-hidden rounded-lg border border-putty-dark sm:grid-cols-3">
        <div className="border-b border-putty-dark bg-ivory p-3 sm:border-b-0 sm:border-r">
          <p className="font-body text-[11px] font-semibold uppercase tracking-wide text-rose-700">Caller claims</p>
          <p className="mt-1 font-body text-sm text-ink">Smuggled discount fields, or a fabricated approval token — bypassing negotiation entirely</p>
        </div>
        <div className="border-b border-putty-dark bg-ivory p-3 sm:border-b-0 sm:border-r">
          <p className="font-body text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Policy Gate does</p>
          <p className="mt-1 font-body text-sm text-ink">Ignores the claim. Re-fetches the real catalog price. Re-derives the allowed discount from merchant_rules.</p>
        </div>
        <div className="bg-ivory p-3">
          <p className="font-body text-[11px] font-semibold uppercase tracking-wide text-moss-dark">Result</p>
          <p className="mt-1 font-body text-sm font-semibold text-moss-dark">✕ BLOCKED — full listed price charged</p>
        </div>
      </div>

      {attack ? (
        <div className="mt-3 rounded-lg border border-putty-dark bg-ivory-deep/40 p-3">
          <p className="font-body text-xs font-semibold text-ink">Real evidence — {attack.attack_id}</p>
          <p className="mt-1 font-body text-xs text-ink-soft">{attack.notes}</p>
          <p className="mt-1 font-body text-[11px] text-ink-soft/60">
            From this project's own red-team suite ({new Date(attack.timestamp).toLocaleDateString()}) — not a third-party audit.
          </p>
        </div>
      ) : (
        <p className="mt-3 font-body text-xs text-ink-soft/60">No recorded price-tampering test result on disk yet.</p>
      )}
    </Card>
  );
}
