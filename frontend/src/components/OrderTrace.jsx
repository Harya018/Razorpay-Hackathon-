import Card from "./Card.jsx";

// "Everything below belongs to THIS order." Renders the ID chain the
// backend assembled from real rows (order_detail.py `trace`). A link the
// backend could not establish renders as unavailable with the backend's
// own reason — never a placeholder ID.
export default function OrderTrace({ trace }) {
  return (
    <Card title="Trace Order" note="Real identifiers only — a missing link is reported, not invented.">
      <ol className="space-y-0">
        {trace.map((t, i) => (
          <li key={t.label} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${t.available ? "bg-moss" : "bg-putty-dark"}`} style={{ marginTop: "0.45rem" }} />
              {i < trace.length - 1 && <span className="w-px flex-1 bg-putty" style={{ minHeight: "1.25rem" }} />}
            </div>
            <div className="min-w-0 flex-1 pb-2.5">
              <p className="font-body text-[11px] uppercase tracking-wide text-ink-soft/60">{t.label}</p>
              {t.available ? (
                <p className="truncate font-mono text-xs text-ink" title={t.value}>{t.value}</p>
              ) : (
                <p className="font-body text-xs text-ink-soft/50">
                  Trace unavailable — {t.note || "backend relationship not currently recorded"}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
