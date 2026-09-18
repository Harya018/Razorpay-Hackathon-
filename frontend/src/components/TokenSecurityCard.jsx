import Card from "./Card.jsx";

// Explanatory card + one real, on-disk red-team result as evidence
// (redteam/results/replay_results.json's replay.approval_token_delayed_reuse
// entry, already surfaced in full by SecurityPosturePanel — this just
// features it). Nothing here is a live simulation; `attack` is passed in
// from the same /dashboard/security-posture fetch the Security page
// already makes, so this never issues its own duplicate request.
export default function TokenSecurityCard({ attack }) {
  return (
    <Card title="Token Security" note="Why a Policy Gate approval can't be treated as permanent authorization.">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <p className="font-body text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Purpose</p>
          <p className="mt-0.5 font-body text-sm text-ink">Single-use authorization</p>
        </div>
        <div>
          <p className="font-body text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Binding</p>
          <p className="mt-0.5 font-body text-sm text-ink">Product, quantity, session — verified atomically on redemption</p>
        </div>
        <div>
          <p className="font-body text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Lifecycle</p>
          <p className="mt-0.5 font-body text-sm text-ink">Issued → Verified → Consumed</p>
        </div>
      </div>

      <p className="mt-3 font-body text-sm text-ink-soft">
        The backend cannot treat a previously approved response as permanent authorization. Every checkout independently
        calls policy-gate's <code className="rounded bg-putty-light px-1 font-mono text-xs">/verify</code>, which atomically
        claims the token (an SQL <code className="rounded bg-putty-light px-1 font-mono text-xs">UPDATE ... WHERE used = 0</code>)
        — a second redemption attempt finds nothing left to claim.
      </p>

      {attack ? (
        <div className="mt-3 rounded-lg border border-putty-dark bg-ivory-deep/40 p-3">
          <div className="flex items-center justify-between">
            <p className="font-body text-xs font-semibold text-ink">Real evidence: token replay attempt</p>
            <span className={`rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold ${attack.verdict === "PASS" ? "bg-moss-light/30 text-moss-dark" : "bg-rose-100 text-rose-700"}`}>
              {attack.verdict === "PASS" ? "✕ TOKEN ALREADY CONSUMED — BLOCKED" : attack.verdict}
            </span>
          </div>
          <p className="mt-1 font-body text-xs text-ink-soft">{attack.description}</p>
          <p className="mt-1 font-body text-[11px] text-ink-soft/60">
            From this project's own red-team suite ({new Date(attack.timestamp).toLocaleDateString()}) — not a third-party audit.
          </p>
        </div>
      ) : (
        <p className="mt-3 font-body text-xs text-ink-soft/60">
          No recorded token-replay test result on disk yet — run the red-team suite's replay category to populate this.
        </p>
      )}
    </Card>
  );
}
