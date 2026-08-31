// Purely presentational — a small pulsing dot + label used anywhere a panel
// is actually receiving live updates (SSE or short-poll), so a viewer can
// see "this is real-time" without being told. Shared across both visual
// registers — "moss" is the storefront's own live/positive accent (see
// storefront-tokens.css); "blue"/"violet"/"emerald" are dashboard/legacy
// tones kept for the dashboard's existing human/agent channel colors.
export default function LiveBadge({ color = "emerald", label = "Live" }) {
  const dot = {
    emerald: "bg-emerald-500",
    blue: "bg-blue-500",
    violet: "bg-violet-500",
    moss: "bg-moss",
  }[color] || "bg-emerald-500";
  const text = {
    emerald: "text-emerald-700",
    blue: "text-blue-700",
    violet: "text-violet-700",
    moss: "text-moss-dark",
  }[color] || "text-emerald-700";
  const bg = {
    emerald: "bg-emerald-50",
    blue: "bg-blue-50",
    violet: "bg-violet-50",
    moss: "bg-moss-light/20",
  }[color] || "bg-emerald-50";

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full ${bg} px-2 py-0.5 text-xs font-medium ${text}`}>
      <span className="relative flex h-2 w-2">
        <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${dot} opacity-75`} />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      {label}
    </span>
  );
}
