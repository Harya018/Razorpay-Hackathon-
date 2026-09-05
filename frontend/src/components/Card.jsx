// Shared light card shell for the consumer-SaaS restyle — white/cream,
// rounded, soft border + subtle shadow. Deliberately NOT used by the
// Audit Trail panel (stays terminal/mono, a different register on
// purpose) or the AI-to-AI conversation view (untouched, out of scope).
export default function Card({ title, note, action, children, className = "" }) {
  return (
    <div className={`rounded-2xl border border-putty-dark bg-white p-4 shadow-sm sm:p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-1 flex items-baseline justify-between gap-2">
          {title && <h2 className="font-body text-xs font-semibold uppercase tracking-wide text-ink-soft">{title}</h2>}
          {action}
        </div>
      )}
      {note && <p className="mb-3 font-body text-[11px] text-ink-soft/70">{note}</p>}
      {children}
    </div>
  );
}
