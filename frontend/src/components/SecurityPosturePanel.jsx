import { useEffect, useState } from "react";

import CardShell from "./Card.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

const CATEGORY_LABELS = {
  concurrency: "Concurrency",
  replay: "Replay",
  injection: "Prompt injection",
  tampering: "Tampering",
  trust_boundary: "Trust boundary",
};

function verdictBadge(verdict) {
  if (verdict === "FAIL") {
    return <span className="rounded-full bg-rose-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-rose-700">FAIL</span>;
  }
  if (verdict === "PASS_CONFIRMS_DOCUMENTED_LIMITATION") {
    return (
      <span className="rounded-full bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-amber-700">
        PASS*
      </span>
    );
  }
  return <span className="rounded-full bg-moss-light/30 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-moss-dark">PASS</span>;
}

function CategoryBar({ label, stat }) {
  const total = stat?.total ?? 0;
  const blocked = stat?.blocked ?? 0;
  const pct = total ? Math.round((blocked / total) * 100) : null;
  return (
    <div className="rounded-lg border border-putty-dark bg-ivory p-3">
      <div className="flex items-center justify-between font-mono text-[11px]">
        <span className="font-medium text-ink-soft">{label}</span>
        <span className="text-ink-soft/60">{total ? `${blocked}/${total}` : "no data"}</span>
      </div>
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-putty-light">
        <div
          className={`h-full ${pct === 100 ? "bg-moss" : pct === null ? "bg-putty-dark" : "bg-amber-500"}`}
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
    </div>
  );
}

// One ledger line — fixed-width, timestamp-first, verdict last, kept in
// mono font deliberately (a scannable log, not a friendly list) even
// though the surrounding frame moved to the light card family.
function AttackRow({ attack }) {
  const [open, setOpen] = useState(false);
  const time = attack.timestamp ? new Date(attack.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--";

  return (
    <div className="border-b border-putty-dark last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="grid w-full grid-cols-[5.5rem_1fr_auto] items-center gap-3 px-3 py-2 text-left font-mono text-xs hover:bg-putty-light/40"
      >
        <span className="shrink-0 text-ink-soft/60">{time}</span>
        <span className="min-w-0 truncate text-ink">
          <span className="text-ink-soft/60">[{CATEGORY_LABELS[attack.category] || attack.category}]</span> {attack.name}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {verdictBadge(attack.verdict)}
          <span className="text-ink-soft/60">{open ? "−" : "+"}</span>
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-putty-dark bg-putty-light/30 px-3 pb-3 pt-2 font-mono text-[11px] text-ink-soft">
          {attack.description && <p className="font-body text-xs text-ink-soft">{attack.description}</p>}
          {attack.notes && (
            <p className="whitespace-pre-wrap border border-putty-dark bg-ivory p-2 text-ink">
              {attack.notes}
            </p>
          )}
          {(attack.requests_sent != null || attack.blocked != null) && (
            <p className="text-ink-soft/60">
              {attack.requests_sent != null && `requests=${attack.requests_sent} `}
              {attack.expected_successes != null && `expected=${attack.expected_successes} `}
              {attack.actual_successes != null && `actual=${attack.actual_successes} `}
              {attack.llm_confused != null && `llm_confused=${String(attack.llm_confused)} `}
              {attack.policy_bypassed != null && `policy_bypassed=${String(attack.policy_bypassed)}`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function SecurityPosturePanel({ refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  // Phase 17: full scorecard shown by default — this is meant to be the
  // second-strongest panel on the dashboard, not a truncated preview a
  // judge has to click through to actually see.
  const [showAll, setShowAll] = useState(true);

  function load() {
    fetch(`${API_BASE_URL}/dashboard/security-posture`)
      .then((res) => res.json())
      .then(setData)
      .catch((err) => setError(err.message));
  }

  useEffect(load, [refreshKey]);

  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;
  if (!data) return <p className="font-body text-sm text-ink-soft">Loading security posture...</p>;

  if (data.total_attacks === 0) {
    return (
      <CardShell title="Security Posture">
        <p className="rounded-lg border border-dashed border-putty-dark bg-ivory p-4 font-mono text-xs text-ink-soft">
          No red-team results found yet — run the suite from <code className="bg-putty-light px-1">redteam</code>{" "}
          (e.g. <code className="bg-putty-light px-1">python -m attacks.concurrency</code>) to populate this panel.
        </p>
      </CardShell>
    );
  }

  const failing = data.attacks.filter((a) => a.verdict === "FAIL");
  const visibleAttacks = showAll ? data.attacks : failing.length ? failing : data.attacks.slice(0, 5);

  return (
    <CardShell
      title="Security Posture"
      action={
        <button type="button" onClick={load} className="font-body text-xs text-clay hover:underline">
          Refresh
        </button>
      }
    >
      {/* Honesty label — deliberately kept as its own visible line, same
          wording, not folded into a tooltip or footnote. */}
      <p className="mb-3 font-body text-[11px] font-medium text-ink-soft">
        From our own red-team suite, run on {data.run_on ? new Date(data.run_on).toLocaleString() : "an unknown date"} —
        not a third-party audit.
      </p>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-putty-dark bg-ivory p-4">
          <p className="font-body text-[11px] font-medium uppercase tracking-wide text-ink-soft">Attacks blocked</p>
          <p className="mt-1 font-body text-2xl font-bold text-ink">
            {data.total_blocked}/{data.total_attacks}
          </p>
        </div>
        <div className="rounded-xl border border-putty-dark bg-ivory p-4">
          <p className="font-body text-[11px] font-medium uppercase tracking-wide text-ink-soft">Open findings</p>
          <p className={`mt-1 font-body text-2xl font-bold ${data.total_findings ? "text-rose-600" : "text-moss-dark"}`}>
            {data.total_findings}
          </p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {Object.entries(data.by_category).map(([key, stat]) => (
          <CategoryBar key={key} label={CATEGORY_LABELS[key] || key} stat={stat} />
        ))}
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-putty-dark bg-ivory">
        <div className="flex items-center justify-between border-b border-putty-dark bg-putty-light/40 px-3 py-2">
          <p className="font-body text-[11px] font-medium text-ink-soft">
            {showAll ? "all attacks" : failing.length ? "open findings" : "recent attacks"}
          </p>
          {data.attacks.length > visibleAttacks.length || (showAll && failing.length !== data.attacks.length) ? (
            <button type="button" onClick={() => setShowAll((s) => !s)} className="font-body text-[11px] text-clay hover:underline">
              {showAll ? "show findings only" : `show all ${data.attacks.length}`}
            </button>
          ) : null}
        </div>
        {visibleAttacks.map((attack) => (
          <AttackRow key={attack.attack_id} attack={attack} />
        ))}
      </div>
    </CardShell>
  );
}
