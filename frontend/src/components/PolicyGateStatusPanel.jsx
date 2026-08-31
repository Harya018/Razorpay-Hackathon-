import { useEffect, useRef, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Polls every 2s specifically so this panel visibly flips to unreachable
// within 2-3 seconds of the policy-gate process actually going down (the
// Phase 14 demo beat) — each poll is a LIVE ping timed by the backend
// right then, never a cached/last-known value.
const POLL_MS = 2000;

function Stat({ label, value }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="font-mono text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}

export default function PolicyGateStatusPanel() {
  const [status, setStatus] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    function poll() {
      fetch(`${API_BASE_URL}/dashboard/policy-gate-status`)
        .then((res) => res.json())
        .then((data) => {
          if (mountedRef.current) setStatus(data);
        })
        .catch(() => {
          if (mountedRef.current) setStatus((prev) => ({ ...(prev || {}), reachable: false }));
        });
    }
    poll();
    const interval = setInterval(poll, POLL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, []);

  if (!status) return <p className="font-mono text-sm text-slate-400">Checking policy-gate...</p>;

  const reachable = status.reachable;

  return (
    <div className={`border p-4 transition-colors ${reachable ? "border-slate-300 bg-content" : "border-rose-500 bg-rose-50"}`}>
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-xs font-semibold uppercase tracking-wide text-slate-500">Policy Gate Status</h2>
        <span
          className={`flex items-center gap-1.5 rounded-sm px-2 py-0.5 font-mono text-[11px] font-semibold ${
            reachable ? "bg-emerald-100 text-emerald-800" : "bg-rose-600 text-white"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${reachable ? "bg-emerald-500" : "bg-white"}`} />
          {reachable ? "Healthy" : "Unreachable"}
        </span>
      </div>
      <p className="mt-0.5 font-mono text-[10px] text-slate-400">
        Separate deployable service, own DB — polled directly every {POLL_MS / 1000}s, not proxied through anything else.
      </p>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Gate uptime" value={reachable ? `${Math.round(status.gate_uptime_seconds ?? 0)}s` : "—"} />
        <Stat label="Live ping" value={reachable ? `${status.live_ping_latency_ms}ms` : `timed out (${status.live_ping_latency_ms}ms)`} />
        <Stat label="Requests evaluated" value={status.total_calls ?? 0} />
        <Stat label="Avg latency" value={status.avg_latency_ms != null ? `${status.avg_latency_ms}ms` : "—"} />
        <Stat label="Approved" value={status.approved ?? 0} />
        <Stat label="Denied" value={status.denied ?? 0} />
        <Stat label="Unreachable calls" value={status.unreachable_calls ?? 0} />
        <Stat label="Checked" value={status.checked_at ? new Date(status.checked_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"} />
      </div>
    </div>
  );
}
