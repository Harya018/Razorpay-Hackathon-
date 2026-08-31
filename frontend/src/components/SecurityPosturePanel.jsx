import { useEffect, useState } from "react";

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
    return <span className="rounded-sm bg-rose-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-rose-700">FAIL</span>;
  }
  if (verdict === "PASS_CONFIRMS_DOCUMENTED_LIMITATION") {
    return (
      <span className="rounded-sm bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-amber-700">
        PASS*
      </span>
    );
  }
  return <span className="rounded-sm bg-emerald-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-700">PASS</span>;
}

function CategoryBar({ label, stat }) {
  const total = stat?.total ?? 0;
  const blocked = stat?.blocked ?? 0;
  const pct = total ? Math.round((blocked / total) * 100) : null;
  return (
    <div className="rounded-sm border border-slate-300 bg-content p-3">
      <div className="flex items-center justify-between font-mono text-[11px]">
        <span className="font-medium text-slate-600">{label}</span>
        <span className="text-slate-400">{total ? `${blocked}/${total}` : "no data"}</span>
      </div>
      <div className="mt-2 h-1 w-full overflow-hidden bg-slate-200">
        <div
          className={`h-full ${pct === 100 ? "bg-emerald-500" : pct === null ? "bg-slate-300" : "bg-amber-500"}`}
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
    </div>
  );
}

// One ledger line — fixed-width, timestamp-first, verdict last. This IS
// the "audit log" surface: a merchant/judge should be able to scan it
// like a log file, not a friendly card list.
function AttackRow({ attack }) {
  const [open, setOpen] = useState(false);
  const time = attack.timestamp ? new Date(attack.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--";

  return (
    <div className="border-b border-slate-200 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="grid w-full grid-cols-[5.5rem_1fr_auto] items-center gap-3 px-3 py-2 text-left font-mono text-xs hover:bg-slate-100"
      >
        <span className="shrink-0 text-slate-400">{time}</span>
        <span className="min-w-0 truncate text-slate-800">
          <span className="text-slate-400">[{CATEGORY_LABELS[attack.category] || attack.category}]</span> {attack.name}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {verdictBadge(attack.verdict)}
          <span className="text-slate-400">{open ? "−" : "+"}</span>
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-200 bg-slate-50 px-3 pb-3 pt-2 font-mono text-[11px] text-slate-600">
          {attack.description && <p className="font-sans text-xs text-slate-600">{attack.description}</p>}
          {attack.notes && (
            <p className="whitespace-pre-wrap border border-slate-300 bg-content p-2 text-slate-700">
              {attack.notes}
            </p>
          )}
          {(attack.requests_sent != null || attack.blocked != null) && (
            <p className="text-slate-400">
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

  if (error) return <p className="text-sm text-rose-400">{error}</p>;
  if (!data) return <p className="text-sm text-slate-400">Loading security posture...</p>;

  if (data.total_attacks === 0) {
    return (
      <div>
        <h2 className="mb-2 font-mono text-xs font-semibold uppercase tracking-wide text-slate-400">Security Posture</h2>
        <p className="rounded-sm border border-dashed border-slate-500 bg-content p-4 font-mono text-xs text-slate-500">
          No red-team results found yet — run the suite from <code className="bg-slate-200 px-1">redteam</code>{" "}
          (e.g. <code className="bg-slate-200 px-1">python -m attacks.concurrency</code>) to populate this panel.
        </p>
      </div>
    );
  }

  const failing = data.attacks.filter((a) => a.verdict === "FAIL");
  const visibleAttacks = showAll ? data.attacks : failing.length ? failing : data.attacks.slice(0, 5);

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="font-mono text-xs font-semibold uppercase tracking-wide text-slate-400">Security Posture</h2>
        <button type="button" onClick={load} className="font-mono text-xs text-blue-400 hover:underline">
          Refresh
        </button>
      </div>
      <p className="mb-3 font-mono text-[11px] text-slate-500">
        From our own red-team suite, run on {data.run_on ? new Date(data.run_on).toLocaleString() : "an unknown date"} —
        not a third-party audit.
      </p>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-sm border border-slate-300 bg-content p-4">
          <p className="font-mono text-[11px] font-medium uppercase tracking-wide text-slate-500">Attacks blocked</p>
          <p className="mt-1 font-mono text-2xl font-bold text-slate-900">
            {data.total_blocked}/{data.total_attacks}
          </p>
        </div>
        <div className="rounded-sm border border-slate-300 bg-content p-4">
          <p className="font-mono text-[11px] font-medium uppercase tracking-wide text-slate-500">Open findings</p>
          <p className={`mt-1 font-mono text-2xl font-bold ${data.total_findings ? "text-rose-600" : "text-emerald-700"}`}>
            {data.total_findings}
          </p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {Object.entries(data.by_category).map(([key, stat]) => (
          <CategoryBar key={key} label={CATEGORY_LABELS[key] || key} stat={stat} />
        ))}
      </div>

      <div className="mt-4 border border-slate-300 bg-content">
        <div className="flex items-center justify-between border-b border-slate-300 px-3 py-2">
          <p className="font-mono text-[11px] font-medium text-slate-500">
            {showAll ? "all attacks" : failing.length ? "open findings" : "recent attacks"}
          </p>
          {data.attacks.length > visibleAttacks.length || (showAll && failing.length !== data.attacks.length) ? (
            <button type="button" onClick={() => setShowAll((s) => !s)} className="font-mono text-[11px] text-blue-600 hover:underline">
              {showAll ? "show findings only" : `show all ${data.attacks.length}`}
            </button>
          ) : null}
        </div>
        {visibleAttacks.map((attack) => (
          <AttackRow key={attack.attack_id} attack={attack} />
        ))}
      </div>
    </div>
  );
}
