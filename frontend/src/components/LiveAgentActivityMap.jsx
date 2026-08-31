// Live mini architecture diagram — Seller Agent and Buyer Agent boxes
// (LLM-driven, dashed violet) both talking to the Policy Gate (100%
// deterministic, solid slate), matching docs/architecture-diagram.svg's
// own legend exactly (slate-200/700 solid = deterministic, violet-100/600
// dashed = LLM-driven). Edge counts start from a real baseline fetched by
// the parent (DashboardHome) and increment live as matching events arrive
// over the dashboard's existing SSE stream — no separate connection here.
function Box({ label, sublabel, variant }) {
  const cls =
    variant === "deterministic"
      ? "border-2 border-slate-600 bg-slate-200 text-slate-800"
      : "border-2 border-dashed border-violet-500 bg-violet-100 text-violet-900";
  return (
    <div className={`flex h-20 w-36 shrink-0 flex-col items-center justify-center px-2 text-center ${cls}`}>
      <p className="font-mono text-xs font-bold">{label}</p>
      <p className="mt-0.5 font-mono text-[9px] opacity-70">{sublabel}</p>
    </div>
  );
}

function Edge({ count }) {
  return (
    <div className="flex flex-1 flex-col items-center px-2">
      <span className="font-mono text-[11px] font-semibold text-slate-500">{count}</span>
      <div className="h-px w-full bg-slate-400" />
      <span className="mt-0.5 font-mono text-[9px] text-slate-400">gate calls</span>
    </div>
  );
}

export default function LiveAgentActivityMap({ sellerToGate, buyerToGate }) {
  return (
    <div>
      <h2 className="mb-1 font-mono text-xs font-semibold uppercase tracking-wide text-slate-500">Live Agent Activity Map</h2>
      <p className="mb-3 font-mono text-[11px] text-slate-400">
        Same deterministic/LLM-driven color coding as the architecture diagram — counts update live from the real event
        stream.
      </p>
      <div className="flex items-center justify-center gap-0 overflow-x-auto border border-slate-300 bg-content p-4">
        <Box label="Seller Agent" sublabel="LLM-driven (human)" variant="llm" />
        <Edge count={sellerToGate} />
        <Box label="Policy Gate" sublabel="100% deterministic" variant="deterministic" />
        <Edge count={buyerToGate} />
        <Box label="Buyer Agent" sublabel="LLM-driven (agent)" variant="llm" />
      </div>
      <div className="mt-2 flex items-center gap-4 font-mono text-[10px] text-slate-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 border-2 border-slate-600 bg-slate-200" /> deterministic
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 border-2 border-dashed border-violet-500 bg-violet-100" /> LLM-driven
        </span>
      </div>
    </div>
  );
}
