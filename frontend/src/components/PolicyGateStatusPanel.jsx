import { useEffect, useRef, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Polls every 2s specifically so this panel visibly flips to unreachable
// within 2-3 seconds of the policy-gate process actually going down (the
// Phase 14 demo beat) — each poll is a LIVE ping timed by the backend
// right then, never a cached/last-known value. Polling logic unchanged
// by the Phase 19 restyle — only the JSX/classes below changed.
const POLL_MS = 2000;

function Stat({ label, value }) {
  return (
    <div>
      <p className="font-body text-[10px] uppercase tracking-wide text-ink-soft/70">{label}</p>
      <p className="font-body text-sm font-semibold text-ink">{value}</p>
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

  if (!status) return <p className="font-body text-sm text-ink-soft">Checking policy-gate...</p>;

  const reachable = status.reachable;

  return (
    <div
      className={`rounded-2xl border p-4 shadow-sm transition-colors sm:p-5 ${
        reachable ? "border-putty-dark bg-white" : "border-rose-400 bg-rose-50"
      }`}
    >
      <div className="flex items-center justify-between">
        <h2 className="font-body text-xs font-semibold uppercase tracking-wide text-ink-soft">Policy Gate Status</h2>
        <span
          className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 font-body text-[11px] font-semibold ${
            reachable ? "bg-moss-light/25 text-moss-dark" : "bg-rose-600 text-white"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${reachable ? "bg-moss" : "bg-white"}`} />
          {reachable ? "Healthy" : "Unreachable"}
        </span>
      </div>
      <p className="mt-0.5 font-body text-[10px] text-ink-soft/70">
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
