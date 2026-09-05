import { useEffect, useRef, useState } from "react";

import CardShell from "./Card.jsx";
import LiveBadge from "./LiveBadge.jsx";
import { humanSessionSummary, translateEvent } from "../utils/eventTranslation.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function statusBadge(session) {
  if (!session.closed) return { text: "in progress", cls: "bg-amber-100 text-amber-800" };
  if (session.final_status === "accepted") return { text: "accepted", cls: "bg-emerald-100 text-emerald-800" };
  if (session.final_status === "rejected") return { text: "rejected", cls: "bg-rose-100 text-rose-800" };
  return { text: session.final_status || "closed", cls: "bg-putty-light text-ink-soft" };
}

// tall (dashboard revamp): this component now lives on its own dedicated
// page (NegotiationsPage) instead of squeezed into a 2-column dashboard
// grid — tall relaxes the max-height and switches to a 2-column card
// grid on wide screens so it actually uses the extra room.
//
// This is an audit-log surface (human negotiation sessions are
// deterministic-graph-driven, not LLM-authored), so each session renders
// as a ledger line — timestamp first, fixed columns, mono — rather than
// a chat-style card. Phase 19: light card family, mono kept for the
// tabular ledger rows specifically. SSE "new entry" tick (ledger-row-tick)
// and the live badge are functionally unchanged.
export default function HumanNegotiationFeed({ refreshKey, tall = false }) {
  const [sessions, setSessions] = useState([]);
  const [newIds, setNewIds] = useState(new Set());
  const [expanded, setExpanded] = useState(null);
  const [showRaw, setShowRaw] = useState(false);
  const listRef = useRef(null);
  const knownIds = useRef(new Set());

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/negotiations?limit=20`)
      .then((res) => res.json())
      .then((data) => {
        // Ledger "new entry" tick: only sessions this feed hasn't shown
        // before flash on insert — never on every refetch of the same rows.
        const fresh = new Set(data.map((s) => s.session_id).filter((id) => !knownIds.current.has(id)));
        knownIds.current = new Set(data.map((s) => s.session_id));
        setNewIds(fresh);
        setSessions(data);
      })
      .catch(() => {});
  }, [refreshKey]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [sessions]);

  return (
    <CardShell
      title="Human Negotiations"
      action={<LiveBadge color="blue" />}
      className="flex flex-col"
    >
      <div
        ref={listRef}
        className={
          tall
            ? "grid max-h-[calc(100vh-260px)] grid-cols-1 gap-3 overflow-y-auto md:grid-cols-2"
            : "max-h-[520px] space-y-2 overflow-y-auto"
        }
      >
        {sessions.length === 0 && <p className="font-mono text-xs text-ink-soft/70">No human negotiations yet.</p>}
        {sessions.map((s) => {
          const badge = statusBadge(s);
          return (
            <div key={s.session_id} className={`rounded-lg border border-putty-dark ${newIds.has(s.session_id) ? "ledger-row-tick" : ""}`}>
              <button
                type="button"
                onClick={() => {
                  setExpanded(expanded === s.session_id ? null : s.session_id);
                  setShowRaw(false);
                }}
                className="grid w-full grid-cols-[5.5rem_1fr_auto] items-center gap-3 px-3 py-2 text-left font-mono text-xs hover:bg-putty-light/40"
              >
                <span className="shrink-0 text-ink-soft/60">{new Date(s.last_updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
                <span className="min-w-0 truncate text-ink">{s.headline}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className={`rounded-full px-1.5 py-0.5 text-[11px] font-medium ${badge.cls}`}>{badge.text}</span>
                  <span className="text-ink-soft/60">{expanded === s.session_id ? "−" : "+"}</span>
                </span>
              </button>
              <p className="px-3 pb-1 font-mono text-[11px] text-ink-soft/60">
                session {s.session_id.slice(0, 8)} - {s.event_count} events
              </p>
              {expanded === s.session_id && (
                <div className="space-y-3 rounded-b-lg border-t border-putty-dark bg-putty-light/30 p-3">
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-[11px]">
                    {humanSessionSummary(s).map((row) => (
                      <div key={row.label} className="contents">
                        <dt className="font-medium text-ink-soft">{row.label}</dt>
                        <dd className="text-ink">{row.value}</dd>
                      </div>
                    ))}
                  </dl>

                  {s.mindset_summary && (
                    <div className="rounded-lg border border-dashed border-violet-400 bg-violet-50 p-2.5">
                      <p className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-violet-500">
                        LLM-generated insight — not a verified customer profile
                      </p>
                      <p className="font-mono text-xs text-violet-800">{s.mindset_summary}</p>
                    </div>
                  )}

                  <ul className="space-y-1.5 border-t border-putty-dark pt-2">
                    {s.events.map((e, i) => {
                      const t = translateEvent(e);
                      return (
                        <li key={i} className="flex items-start justify-between gap-2 font-mono text-[11px]">
                          <span className="text-ink-soft">{t.sentence}</span>
                          <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${t.badge.cls}`}>
                            {t.badge.text}
                          </span>
                        </li>
                      );
                    })}
                  </ul>

                  <button
                    type="button"
                    className="font-mono text-[11px] font-medium text-ink-soft/60 hover:text-ink-soft"
                    onClick={() => setShowRaw((v) => !v)}
                  >
                    {showRaw ? "Hide raw event data" : "Raw event data"}
                  </button>
                  {showRaw && (
                    <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-putty-dark bg-ivory p-2 font-mono text-[11px] text-ink-soft">
                      {JSON.stringify(s.events, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </CardShell>
  );
}
