import { useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Register 2 stat card — a "readout" set into the dark instrument
// housing: cool-white content surface, sharp corners (no rounded-casual
// cards pretending this is a friendly admin panel), the actual number in
// monospace since it's the kind of figure an operator would want to
// read precisely and compare across cards, not prose.
function Card({ label, value, sub, accent = "slate" }) {
  const valueColor = { slate: "text-slate-900", emerald: "text-emerald-700" }[accent] || "text-slate-900";
  return (
    <div className="rounded-sm border border-slate-300 bg-content p-4">
      <p className="font-mono text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-bold ${valueColor}`}>{value}</p>
      {sub && <p className="mt-1 font-mono text-[11px] text-slate-400">{sub}</p>}
    </div>
  );
}

export default function SalesSummaryPanel({ refreshKey }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  function load() {
    fetch(`${API_BASE_URL}/dashboard/summary`)
      .then((res) => res.json())
      .then(setSummary)
      .catch((err) => setError(err.message));
  }

  useEffect(load, [refreshKey]);

  // Fallback poll so the panel stays fresh even if an SSE event was missed.
  useEffect(() => {
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <p className="text-sm text-rose-400">{error}</p>;
  if (!summary) return <p className="text-sm text-slate-400">Loading sales overview...</p>;

  const rupees = (v) => `Rs ${(v ?? 0).toFixed(2)}`;

  return (
    <div>
      <h2 className="mb-2 font-mono text-xs font-semibold uppercase tracking-wide text-slate-400">Sales Overview</h2>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card label="Total orders" value={summary.total_orders} />
        <Card label="Total revenue" value={rupees(summary.total_revenue)} />
        <Card
          label="Recovered via negotiation"
          value={rupees(summary.revenue_recovered_via_negotiation)}
          sub={`${summary.discounted_order_count} discounted orders`}
          accent="emerald"
        />
        <Card
          label="Human vs AI-agent revenue"
          value={`${rupees(summary.channel_breakdown.human.revenue)} / ${rupees(summary.channel_breakdown.agent.revenue)}`}
          sub={`${summary.channel_breakdown.human.orders} human - ${summary.channel_breakdown.agent.orders} agent orders`}
        />
      </div>
    </div>
  );
}
