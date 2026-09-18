import { useEffect, useState } from "react";

const AUTO_DISMISS_MS = 5000;

const KIND_CLASS = {
  info: "border-putty-dark bg-white text-ink",
  success: "border-moss-light bg-moss-light/20 text-moss-dark",
  error: "border-rose-300 bg-rose-50 text-rose-700",
};
const KIND_ICON = { info: "ℹ", success: "✓", error: "✕" };

// Mounted once (App.jsx) — replaces scattered ad-hoc status <p> tags and
// browser alert()s with a consistent, dismissible, auto-expiring notice.
// Purely presentational: every message it shows was pushed by a real
// event elsewhere (checkout result, negotiation error, etc.) via
// lib/toast.js — this component fabricates nothing.
export default function ToastHost() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    function onToast(e) {
      const t = e.detail;
      setToasts((prev) => [...prev, t]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((x) => x.id !== t.id));
      }, AUTO_DISMISS_MS);
    }
    window.addEventListener("app:toast", onToast);
    return () => window.removeEventListener("app:toast", onToast);
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-[100] flex flex-col items-center gap-2 px-4 sm:items-end sm:right-4 sm:left-auto">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`pointer-events-auto flex w-full max-w-sm items-start gap-2 rounded-lg border px-3.5 py-2.5 font-body text-sm shadow-md ${KIND_CLASS[t.kind] || KIND_CLASS.info}`}
        >
          <span className="mt-0.5 shrink-0 font-semibold" aria-hidden="true">{KIND_ICON[t.kind] || KIND_ICON.info}</span>
          <span className="min-w-0 flex-1">{t.message}</span>
          <button
            onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            className="shrink-0 opacity-60 hover:opacity-100"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
