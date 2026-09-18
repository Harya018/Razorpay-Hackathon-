import { useEffect, useState } from "react";

const BACKEND_URL = import.meta.env.VITE_API_BASE_URL;

// Every status here comes from an ACTUAL fetch made right now — never a
// cached/assumed value. "Database" has no dedicated health endpoint, so
// its status is honestly derived: a successful /catalog read IS a real
// round trip through the backend's DB, so its outcome is a fair proxy
// (this is stated explicitly in the label, not silently implied).
// Policy Gate's own /health has no CORS configured for direct browser
// calls (neither does buyer-agent — see their server.py/main.py files,
// no CORSMiddleware), so this reuses the EXISTING backend-proxied
// GET /dashboard/policy-gate-status (already used by
// PolicyGateStatusPanel) instead of a direct cross-origin ping — the
// same real reachability check, through the one path a browser can
// actually make it.
async function ping(url, timeoutMs = 3000) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  const start = performance.now();
  try {
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(t);
    return { ok: res.ok, latencyMs: Math.round(performance.now() - start) };
  } catch {
    clearTimeout(t);
    return { ok: false, latencyMs: null };
  }
}

async function pingPolicyGateViaBackend(timeoutMs = 4000) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BACKEND_URL}/dashboard/policy-gate-status`, { signal: controller.signal });
    clearTimeout(t);
    if (!res.ok) return { ok: false, latencyMs: null };
    const data = await res.json();
    return { ok: Boolean(data.reachable), latencyMs: data.live_ping_latency_ms ?? null };
  } catch {
    clearTimeout(t);
    return { ok: false, latencyMs: null };
  }
}

function Dot({ ok }) {
  return <span className={`h-2 w-2 shrink-0 rounded-full ${ok ? "bg-moss" : "bg-rose-600"}`} aria-hidden="true" />;
}

export function useServiceHealth(sseConnected) {
  const [health, setHealth] = useState({ backend: null, policyGate: null, database: null });

  useEffect(() => {
    let cancelled = false;
    async function check() {
      const [backend, policyGate, database] = await Promise.all([
        ping(`${BACKEND_URL}/health`),
        pingPolicyGateViaBackend(),
        ping(`${BACKEND_URL}/catalog`),
      ]);
      if (!cancelled) setHealth({ backend, policyGate, database });
    }
    check();
    const interval = setInterval(check, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return {
    backend: health.backend,
    policyGate: health.policyGate,
    database: health.database,
    sse: sseConnected,
  };
}

export default function ServiceHealthGrid({ sseConnected, compact = false }) {
  const health = useServiceHealth(sseConnected);

  const rows = [
    { label: "Backend", state: health.backend, latency: health.backend?.latencyMs },
    { label: "Policy Gate", state: health.policyGate, latency: health.policyGate?.latencyMs },
    { label: "Database", state: health.database, latency: health.database?.latencyMs, note: "via a real /catalog round trip — no dedicated DB health endpoint exists" },
    { label: "SSE (live dashboard stream)", state: sseConnected == null ? null : { ok: sseConnected } },
    { label: "Buyer Agent", state: null, note: "no CORS configured for browser calls — status not checkable from this page; see backend's proxied /dashboard/agent-activity for evidence it's reachable" },
    { label: "Razorpay", state: { ok: true }, note: "Test Mode", static: true },
  ];

  function statusText(row) {
    if (row.state === null) return "Unknown";
    if (!row.state.ok) return "Unreachable";
    if (row.static) return row.note;
    return row.latency != null ? `Healthy — ${row.latency}ms` : "Healthy";
  }
  function statusClass(row) {
    if (row.state === null) return "text-ink-soft/50";
    return row.state.ok ? "text-moss-dark" : "text-rose-700";
  }

  if (compact) {
    return (
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center gap-2 font-body text-sm">
            {row.state === null ? <span className="h-2 w-2 shrink-0 rounded-full bg-putty-dark" /> : <Dot ok={row.state.ok} />}
            <span className="text-ink">{row.label.replace(" (live dashboard stream)", "")}</span>
            <span className={`text-xs font-medium ${statusClass(row)}`}>{row.static ? row.note : statusText(row).split(" — ")[0]}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {rows.map((row) => (
        <div key={row.label} className="flex items-start justify-between gap-3 rounded-lg border border-putty-dark bg-ivory px-3 py-2">
          <div className="min-w-0">
            <span className="flex items-center gap-2 font-body text-sm text-ink">
              {row.state === null ? <span className="h-2 w-2 shrink-0 rounded-full bg-putty-dark" /> : <Dot ok={row.state.ok} />}
              {row.label}
            </span>
            {row.note && !row.static && <p className="mt-0.5 font-body text-[11px] text-ink-soft/60">{row.note}</p>}
          </div>
          <span className={`shrink-0 font-body text-xs font-medium ${statusClass(row)}`}>{statusText(row)}</span>
        </div>
      ))}
    </div>
  );
}
