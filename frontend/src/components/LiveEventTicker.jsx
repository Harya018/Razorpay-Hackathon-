import Card from "./Card.jsx";
import LiveBadge from "./LiveBadge.jsx";
import { translateEvent } from "../utils/eventTranslation.js";

// Purely presentational: renders the real-time SSE feed (GET
// /dashboard/stream) as a chronological ticker. The page that renders
// this owns the single SSE connection (via hooks/useLiveEvents.js) and
// passes the buffered events in — every line is a real audit_log write,
// translated via the same eventTranslation.js dictionary the negotiation
// feeds use, never synthesized here.
export default function LiveEventTicker({ events, connected, limit = 12 }) {
  const visible = events.slice(0, limit);

  return (
    <Card
      title="Live Activity"
      action={connected ? <LiveBadge color="moss" /> : <span className="font-body text-xs text-ink-soft/60">connecting...</span>}
    >
      {visible.length === 0 ? (
        <p className="font-body text-sm text-ink-soft/60">No activity yet — negotiate, or start an AI buyer agent, to see events here.</p>
      ) : (
        <ul className="space-y-1.5">
          {visible.map((e) => {
            const t = translateEvent(e);
            return (
              <li key={e.id} className="flex items-start justify-between gap-3 border-b border-putty-light py-1.5 last:border-0">
                <div className="min-w-0 flex-1">
                  <span className="mr-2 font-mono text-[11px] text-ink-soft/50">
                    {new Date(e.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  <span className="font-body text-sm text-ink">{t.sentence}</span>
                </div>
                <span className={`shrink-0 rounded-full px-1.5 py-0.5 font-body text-[10px] font-medium ${t.badge.cls}`}>{t.badge.text}</span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
