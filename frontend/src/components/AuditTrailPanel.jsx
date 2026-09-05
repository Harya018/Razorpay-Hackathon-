import { useEffect, useState } from "react";

import CardShell from "./Card.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Phase 19 shell rebuild: every OTHER dashboard panel moved to the light
// cream/warm-brown card family — this one deliberately did not. The
// mono font + slate/terminal palette below is UNCHANGED; only the outer
// frame (via CardShell) picks up the new rounded/shadow card rhythm so
// it still sits in the same grid as everything else without looking
// like a rendering mistake. That visual distinction — "this one panel
// looks like a terminal" — is the point: it signals tamper-evident log,
// not a styling oversight.

function ChainLink({ entry, isFirst }) {
  return (
    <div>
      {!isFirst && <div className="ml-4 h-3 w-px bg-white/15" />}
      <div className="flex items-start gap-3 border border-white/10 bg-panel-raised px-3 py-2">
        <div className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-slate-500" />
        <div className="min-w-0 flex-1 font-mono text-[11px]">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-200">{entry.event_type}</span>
            <span className="shrink-0 text-slate-500">{new Date(entry.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
          </div>
          <p className="mt-1 truncate text-slate-500" title={entry.previous_hash}>
            prev: <span className="text-slate-400">{entry.previous_hash_short}</span>
          </p>
          <p className="truncate text-slate-500" title={entry.entry_hash}>
            hash: <span className="font-semibold text-slate-300">{entry.entry_hash_short}</span>
          </p>
        </div>
      </div>
    </div>
  );
}

function VerifyResultBanner({ result }) {
  if (!result) return null;
  if (result.valid === null) {
    return <p className="mt-2 font-mono text-[11px] text-slate-500">No chain to verify yet.</p>;
  }
  if (result.valid) {
    return (
      <p className="mt-2 border border-emerald-800 bg-emerald-950/50 px-3 py-2 font-mono text-[11px] font-medium text-emerald-400">
        ✓ Chain verified — {result.total_rows} entries, unbroken.
      </p>
    );
  }
  return (
    <p className="mt-2 border border-rose-800 bg-rose-950/50 px-3 py-2 font-mono text-[11px] font-medium text-rose-400">
      ✗ Chain broken at entry #{result.broken_at_row_id} — {result.reason}
    </p>
  );
}

export default function AuditTrailPanel({ refreshKey }) {
  const [chain, setChain] = useState(null);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifying, setVerifying] = useState(false);

  const [sandbox, setSandbox] = useState(null);
  const [sandboxVerifyResult, setSandboxVerifyResult] = useState(null);
  const [sandboxBusy, setSandboxBusy] = useState(false);

  function loadChain() {
    fetch(`${API_BASE_URL}/dashboard/audit-trail`)
      .then((res) => res.json())
      .then(setChain)
      .catch(() => {});
  }
  function loadSandbox() {
    fetch(`${API_BASE_URL}/dashboard/audit-trail/sandbox`)
      .then((res) => res.json())
      .then(setSandbox)
      .catch(() => {});
  }

  useEffect(() => {
    loadChain();
    setVerifyResult(null);
  }, [refreshKey]);

  async function handleVerify() {
    setVerifying(true);
    try {
      const res = await fetch(`${API_BASE_URL}/dashboard/audit-trail/verify`, { method: "POST" });
      setVerifyResult(await res.json());
    } finally {
      setVerifying(false);
    }
  }

  async function handleSandboxAction(path) {
    setSandboxBusy(true);
    try {
      const res = await fetch(`${API_BASE_URL}/dashboard/audit-trail/sandbox${path}`, { method: "POST" });
      const data = await res.json();
      if (path === "/verify") {
        setSandboxVerifyResult(data);
      } else {
        setSandbox(data);
        setSandboxVerifyResult(null);
      }
    } finally {
      setSandboxBusy(false);
    }
  }

  if (!chain) {
    return (
      <CardShell className="!bg-panel">
        <p className="font-mono text-sm text-slate-400">Loading audit trail...</p>
      </CardShell>
    );
  }

  return (
    <CardShell className="!border-slate-700 !bg-panel">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="font-mono text-xs font-semibold uppercase tracking-wide text-slate-400">Audit Trail</h2>
        <button type="button" onClick={loadChain} className="font-mono text-xs text-blue-400 hover:underline">
          Refresh
        </button>
      </div>

      {chain.chain_key ? (
        <>
          <p className="mb-2 font-mono text-[11px] text-slate-500">
            Most recently active chain: <span className="text-slate-300">{chain.chain_key}</span> — last {chain.count} entries, oldest
            first. Each entry's <span className="text-slate-300">prev</span> hash links to the entry above it.
          </p>
          <div className="max-h-80 space-y-0 overflow-y-auto border border-white/10 bg-panel p-3">
            {chain.entries.map((entry, i) => (
              <ChainLink key={entry.id} entry={entry} isFirst={i === 0} />
            ))}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={handleVerify}
              disabled={verifying}
              className="rounded-sm bg-slate-200 px-3 py-1.5 font-mono text-xs font-medium text-panel hover:bg-white disabled:bg-slate-600 disabled:text-slate-400"
            >
              {verifying ? "Verifying..." : "Verify Chain Integrity"}
            </button>
            <span className="font-mono text-[11px] text-slate-500">Recomputes every hash server-side, right now.</span>
          </div>
          <VerifyResultBanner result={verifyResult} />
        </>
      ) : (
        <p className="border border-dashed border-slate-600 bg-panel p-4 font-mono text-xs text-slate-500">
          No negotiation activity yet — the hash chain populates as real negotiation/order events are written.
        </p>
      )}

      {/* Sandbox: a synthetic chain, written through the exact same real
          write_audit_log()/verify_chain() code path, so a judge can watch
          tamper detection fire live without touching real negotiation
          data. */}
      <div className="mt-4 border-t border-white/10 pt-3">
        <button
          type="button"
          onClick={() => {
            if (!sandbox) loadSandbox();
          }}
          className="font-mono text-[11px] font-medium text-slate-500 hover:text-slate-300"
        >
          {sandbox ? "Tamper-detection sandbox (synthetic chain, safe to break)" : "Try breaking the chain →"}
        </button>

        {sandbox && (
          <div className="mt-2">
            <div className="space-y-0 border border-white/10 bg-panel p-3">
              {sandbox.entries.map((entry, i) => (
                <ChainLink key={entry.id} entry={entry} isFirst={i === 0} />
              ))}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={sandboxBusy}
                onClick={() => handleSandboxAction("/tamper")}
                className="rounded-sm bg-rose-700 px-3 py-1.5 font-mono text-xs font-medium text-white hover:bg-rose-600 disabled:bg-rose-950 disabled:text-rose-800"
              >
                Corrupt an entry
              </button>
              <button
                type="button"
                disabled={sandboxBusy}
                onClick={() => handleSandboxAction("/verify")}
                className="rounded-sm bg-slate-200 px-3 py-1.5 font-mono text-xs font-medium text-panel hover:bg-white disabled:bg-slate-600 disabled:text-slate-400"
              >
                Verify sandbox chain
              </button>
              <button
                type="button"
                disabled={sandboxBusy}
                onClick={() => handleSandboxAction("/reset")}
                className="font-mono text-xs text-slate-500 hover:text-slate-300"
              >
                Reset
              </button>
            </div>
            <VerifyResultBanner result={sandboxVerifyResult} />
          </div>
        )}
      </div>
    </CardShell>
  );
}
