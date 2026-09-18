// Small shared UI primitives for the commerce pages — status badges,
// a confirm modal, skeleton rows, and the money formatter. Kept together
// deliberately: they are tiny, and every order/inventory page uses all
// of them.

export const rupees = (paise) => (paise == null ? "—" : `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");

const TONE = {
  success: "bg-moss-light/25 text-moss-dark",
  warning: "bg-amber-100 text-amber-800",
  error: "bg-rose-100 text-rose-700",
  neutral: "bg-putty-light text-ink-soft",
  info: "bg-blue-50 text-blue-800",
};

// Order payment status -> tone/label (backend `status`: created|paid|failed)
export function paymentBadge(status) {
  return { paid: ["success", "Paid"], failed: ["error", "Failed"], created: ["warning", "Pending"] }[status] || ["neutral", status || "—"];
}

export function fulfillmentBadge(status, labels = {}) {
  if (!status) return ["neutral", "Not started"];
  const tone = status === "delivered" ? "success" : status === "placed" ? "info" : "warning";
  return [tone, labels[status] || status];
}

export function Badge({ tone = "neutral", children }) {
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 font-body text-[11px] font-semibold ${TONE[tone]}`}>{children}</span>;
}

export function ConfirmModal({ open, title, body, confirmLabel = "Confirm", danger = false, onCancel, onConfirm, busy }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-ink/40 p-4" onClick={onCancel}>
      <div className="w-full max-w-md rounded-2xl border border-putty-dark bg-white p-5 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <p className="font-display text-lg font-semibold text-ink">{title}</p>
        <div className="mt-2 font-body text-sm text-ink-soft">{body}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} disabled={busy} className="rounded-lg border border-putty-dark px-4 py-2 font-body text-sm font-medium text-ink-soft hover:bg-putty-light">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-lg px-4 py-2 font-body text-sm font-semibold text-ivory shadow-sm disabled:opacity-60 ${danger ? "bg-rose-600 hover:bg-rose-700" : "bg-clay hover:bg-clay-dark"}`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function SkeletonRows({ rows = 4 }) {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 rounded-md bg-putty-light" />
      ))}
    </div>
  );
}

export function Empty({ title, body }) {
  return (
    <div className="rounded-md border border-dashed border-putty-dark bg-ivory p-8 text-center">
      <p className="font-body text-sm font-medium text-ink">{title}</p>
      {body && <p className="mt-1 font-body text-xs text-ink-soft/70">{body}</p>}
    </div>
  );
}

export function ErrorBox({ message }) {
  return <p className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 font-body text-sm text-rose-700">{message}</p>;
}

export function Field({ label, children, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 font-body text-sm">
      <span className="text-ink-soft">{label}</span>
      <span className={`text-right text-ink ${mono ? "font-mono text-xs" : ""}`}>{children ?? "—"}</span>
    </div>
  );
}

// Consistent, user-facing wording for backend failures — never a stack trace.
export async function readError(res, fallback) {
  const body = await res.json().catch(() => ({}));
  const detail = typeof body.detail === "string" ? body.detail : null;
  if (res.status === 401) return "Your session has expired — please sign in again.";
  if (res.status === 403) return "You don't have permission to do that.";
  if (res.status === 404) return detail || "Not found.";
  if (res.status === 503) return detail || "A required service is unavailable right now.";
  return detail || fallback;
}
