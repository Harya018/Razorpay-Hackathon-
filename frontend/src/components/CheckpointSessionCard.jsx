import { useEffect, useState } from "react";

import Card from "./Card.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Reads GET /negotiate/{session_id}/status — real, live visibility into
// the same in-memory expiry tracking the backend already enforces as a
// side effect of /negotiate/message. sessionId defaults to the most
// recently active session (from /dashboard/negotiations) if none is
// passed in.
export default function CheckpointSessionCard({ sessionId: sessionIdProp }) {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(sessionIdProp ?? null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (sessionIdProp) return;
    fetch(`${API_BASE_URL}/dashboard/negotiations?limit=20`)
      .then((res) => res.json())
      .then((data) => {
        setSessions(data);
        setSessionId(data[0]?.session_id ?? null);
      })
      .catch(() => {});
  }, [sessionIdProp]);

  useEffect(() => {
    if (!sessionId) return;
    fetch(`${API_BASE_URL}/negotiate/${sessionId}/status`)
      .then((res) => res.json())
      .then(setStatus)
      .catch((err) => setError(err.message));
  }, [sessionId]);

  return (
    <Card title="LangGraph Session">
      <p className="mb-3 font-body text-xs text-ink-soft/70">
        The LLM does not remember the workflow by itself — LangGraph checkpointing stores the application's workflow
        state, independent of any model call.
      </p>

      {!sessionIdProp && sessions.length > 0 && (
        <label className="mb-3 flex items-center gap-2 font-body text-xs text-ink-soft">
          Session:
          <select
            value={sessionId ?? ""}
            onChange={(e) => setSessionId(e.target.value)}
            className="rounded-sm border border-putty-dark bg-ivory px-2 py-1 font-mono text-[11px] text-ink"
          >
            {sessions.map((s) => (
              <option key={s.session_id} value={s.session_id}>
                {s.session_id.slice(0, 8)} — {s.headline}
              </option>
            ))}
          </select>
        </label>
      )}

      {error && <p className="font-body text-sm text-rose-700">{error}</p>}
      {!status && !error && sessionId && <p className="font-body text-sm text-ink-soft">Loading...</p>}
      {!sessionId && sessions.length === 0 && <p className="font-body text-sm text-ink-soft/60">No sessions recorded yet.</p>}

      {status && (
        <div className="space-y-1.5 font-body text-sm">
          <div className="flex justify-between"><span className="text-ink-soft">Session ID</span><span className="font-mono text-xs text-ink">{status.session_id.slice(0, 8)}...</span></div>
          <div className="flex justify-between">
            <span className="text-ink-soft">Checkpoint</span>
            <span className={`font-medium ${!status.exists ? "text-ink-soft/50" : status.expired ? "text-rose-700" : "text-moss-dark"}`}>
              {!status.exists ? "Not tracked by this process (restarted since, or never here)" : status.expired ? "Expired" : "Available"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-soft">Status</span>
            <span className={`font-medium ${status.resumable ? "text-moss-dark" : "text-ink-soft/50"}`}>
              {status.resumable ? "Resumable" : status.exists && !status.expired ? "Already closed" : "Cannot resume"}
            </span>
          </div>
          <div className="flex justify-between"><span className="text-ink-soft">Session expiry</span><span className="text-ink">{status.session_max_age_seconds / 60} minutes</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">Persistence</span><span className="text-ink">In-memory (LangGraph MemorySaver)</span></div>
          {status.expires_at && (
            <div className="flex justify-between"><span className="text-ink-soft">Expires at</span><span className="text-ink">{new Date(status.expires_at * 1000).toLocaleTimeString()}</span></div>
          )}
        </div>
      )}
    </Card>
  );
}
