import { useEffect, useState } from "react";

import CardShell from "./Card.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Phase 18.3 — the actual methodology behind the simulated number,
// sitting directly next to it rather than only in metrics/recovery_sim.py's
// own docstring. Every fact here is copied from that file's real
// MODEL DOCUMENTATION section — this is not a separate, looser retelling.
// Phase 19: wording UNCHANGED, only the light-card colors below it.
function MethodologyNote() {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="font-body text-[11px] font-medium text-clay hover:underline"
      >
        {open ? "Hide methodology ▲" : "How is this number calculated? ▼"}
      </button>
      {open && (
        <div className="mt-2 space-y-2 rounded-lg border border-putty-dark bg-ivory p-3 font-body text-[11px] text-ink">
          <p>
            <strong>What's real:</strong> every simulated session runs the actual storefront negotiation flow —
            real <code className="bg-putty-light px-1">POST /negotiate/start</code>/
            <code className="bg-putty-light px-1">/negotiate/message</code> calls, the real discount ladder (5% then
            10%), and the real Policy Gate approving or rejecting each offer. Nothing about the negotiation logic
            itself is mocked.
          </p>
          <p>
            <strong>What's simulated:</strong> whether a shopper accepts a given offer. There is no real customer in
            this harness. Each simulated shopper draws one number,{" "}
            <code className="bg-putty-light px-1">required_discount_pct ~ Uniform(0, 20)</code> — "the smallest
            discount this shopper would have accepted" — and accepts the first REAL offer whose actual discount
            percentage meets or exceeds it.
          </p>
          <p>
            <strong>Formula:</strong> since the real ladder only ever offers 5% or 10% (with a 3rd "final offer"
            framing of the same 10%), Uniform(0, 20) implies ~25% of simulated shoppers are satisfied by 5%, ~25%
            more by 10%, and the remaining ~50% would need more than this merchant's ceiling ever offers — they
            should never convert on price alone. One additional rule: the final rung gets a flat{" "}
            <code className="bg-putty-light px-1">+15%</code> acceptance chance purely from "this is truly our best
            price" urgency framing, independent of price — applied nowhere else.
          </p>
          <p>
            <strong>Calibrated against:</strong> nothing. This project has no real shopper conversion data to
            calibrate against — the Uniform(0, 20) bound and the 15% urgency figure are stated, disclosed
            assumptions, not measurements. Changing either would materially change every headline number below;
            that sensitivity is deliberately not hidden behind a single clean percentage.
          </p>
          <p className="text-amber-700">
            <strong>What this number is NOT:</strong> a claim about real-world conversion rates. It's a controlled
            estimate of what the discount ladder mechanism <em>could</em> recover under this one disclosed
            behavior model. See <code className="bg-putty-light px-1">metrics/recovery_sim.py</code>'s own
            module docstring for the unabridged version, and the Sales Analytics page's "Discount Tier Breakdown
            (Real)" card for what has actually happened in real negotiations, which is a separate, non-simulated
            number.
          </p>
        </div>
      )}
    </div>
  );
}

export default function RecoverySimulationPanel({ refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  function load() {
    fetch(`${API_BASE_URL}/dashboard/recovery-simulation`)
      .then((res) => res.json())
      .then(setData)
      .catch((err) => setError(err.message));
  }

  useEffect(load, [refreshKey]);

  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;
  if (!data) return <p className="font-body text-sm text-ink-soft">Loading recovery simulation...</p>;

  if (!data.available || !data.summary) {
    return (
      <CardShell title="Revenue Recovery (Simulated)">
        <p className="rounded-lg border border-dashed border-putty-dark bg-ivory p-4 font-body text-xs text-ink-soft">
          No simulation results yet — run <code className="bg-putty-light px-1">python recovery_sim.py</code> from{" "}
          <code className="bg-putty-light px-1">metrics/</code> to populate this card.
        </p>
      </CardShell>
    );
  }

  const s = data.summary;
  const rupees = (paise) => `Rs ${((paise ?? 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  const pct = Math.round((s.recovery_rate ?? 0) * 100);

  return (
    <CardShell
      title="Revenue Recovery (Simulated)"
      action={
        <button type="button" onClick={load} className="font-body text-xs text-clay hover:underline">
          Refresh
        </button>
      }
    >
      {/* Honesty banner — wording unchanged, same prominence (first thing
          under the header, full width, not collapsed into a tooltip). */}
      <p className="mb-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 font-body text-[11px] text-amber-800">
        <strong>Simulation-derived, not real shopper data.</strong> Customer acceptance is modeled (see the run's own
        model_documentation) — this is a controlled estimate of what the discount ladder could recover under a
        disclosed acceptance distribution, not a measured real-world rate.
      </p>

      <MethodologyNote />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-putty-dark bg-ivory p-4">
          <p className="font-body text-[11px] font-medium uppercase tracking-wide text-ink-soft">Recovery rate</p>
          <p className="mt-1 font-body text-2xl font-bold text-moss-dark">{pct}%</p>
          <p className="mt-1 font-body text-[11px] text-ink-soft/70">
            {s.conversions}/{s.sessions_usable} simulated carts
          </p>
        </div>
        <div className="rounded-xl border border-putty-dark bg-ivory p-4">
          <p className="font-body text-[11px] font-medium uppercase tracking-wide text-ink-soft">Revenue recovered</p>
          <p className="mt-1 font-body text-2xl font-bold text-ink">{rupees(s.total_recovered_revenue_paise)}</p>
          <p className="mt-1 font-body text-[11px] text-ink-soft/70">across this run</p>
        </div>
        <div className="rounded-xl border border-putty-dark bg-ivory p-4">
          <p className="font-body text-[11px] font-medium uppercase tracking-wide text-ink-soft">Avg. discount given</p>
          <p className="mt-1 font-body text-2xl font-bold text-ink">
            {s.avg_discount_pct_among_conversions != null ? `${s.avg_discount_pct_among_conversions.toFixed(1)}%` : "--"}
          </p>
          <p className="mt-1 font-body text-[11px] text-ink-soft/70">among conversions</p>
        </div>
        <div className="rounded-xl border border-putty-dark bg-ivory p-4">
          <p className="font-body text-[11px] font-medium uppercase tracking-wide text-ink-soft">Which tier closed it</p>
          <div className="mt-1 space-y-0.5 font-body text-[11px] text-ink-soft">
            {Object.entries(s.closing_tier_breakdown || {}).length ? (
              Object.entries(s.closing_tier_breakdown).map(([tier, count]) => (
                <p key={tier}>
                  {tier}: <span className="font-semibold text-ink">{count}</span>
                </p>
              ))
            ) : (
              <p>no conversions this run</p>
            )}
          </div>
        </div>
      </div>

      <p className="mt-2 font-body text-[11px] text-ink-soft/70">
        n={s.sessions_requested}, seed={s.rng_seed} (reproducible) - run on {new Date(s.generated_at).toLocaleString()}
        {s.sessions_errored ? ` - ${s.sessions_errored} session(s) errored` : ""}
      </p>
    </CardShell>
  );
}
