import { useEffect, useState } from "react";

import CardShell from "./Card.jsx";
import Sparkline from "./Sparkline.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Phase 19 shell rebuild: light consumer-SaaS stat tile — white surface,
// rounded corners, soft border. The sparkline prop is OPTIONAL and only
// ever passed a real, already-computed time series (see below) — never
// added to a stat that doesn't have one.
function StatTile({ label, value, sub, accent = "ink", sparkline }) {
  const valueColor = { ink: "text-ink", emerald: "text-moss-dark" }[accent] || "text-ink";
  return (
    <div className="rounded-xl border border-putty-dark bg-ivory p-4">
      <p className="font-body text-[11px] font-medium uppercase tracking-wide text-ink-soft">{label}</p>
      <div className="mt-1 flex items-end justify-between gap-2">
        <p className={`font-body text-2xl font-bold ${valueColor}`}>{value}</p>
        {sparkline && <Sparkline points={sparkline} />}
      </div>
      {sub && <p className="mt-1 font-body text-[11px] text-ink-soft/70">{sub}</p>}
    </div>
  );
}

export default function SalesSummaryPanel({ refreshKey }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  // Real revenue-over-time series, reused from the SAME endpoint the
  // Sales Analytics page already calls (GET /dashboard/analytics) — no
  // new backend route, no new data shape. Only "Total revenue" gets a
  // sparkline because this is the only Sales Overview stat with an
  // already-computed time series behind it; the others (total orders,
  // recovered-via-negotiation, human/agent split) are point-in-time
  // aggregates from /dashboard/summary with no bucketed history to draw.
  const [revenueSeries, setRevenueSeries] = useState(null);
  const [funnel, setFunnel] = useState(null);

  function load() {
    fetch(`${API_BASE_URL}/dashboard/summary`)
      .then((res) => res.json())
      .then(setSummary)
      .catch((err) => setError(err.message));
  }

  useEffect(load, [refreshKey]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/analytics`)
      .then((res) => res.json())
      .then((data) => {
        setRevenueSeries((data.revenue_over_time || []).map((p) => p.revenue));
        setFunnel(data.negotiation_funnel || null);
      })
      .catch(() => {});
  }, [refreshKey]);

  // Fallback poll so the panel stays fresh even if an SSE event was missed.
  useEffect(() => {
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;
  if (!summary) return <p className="font-body text-sm text-ink-soft">Loading sales overview...</p>;

  const rupees = (v) => `Rs ${(v ?? 0).toFixed(2)}`;

  return (
    <CardShell title="Sales Overview">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Total orders" value={summary.total_orders} sub={`${summary.orders_by_status?.paid ?? 0} paid`} />
        <StatTile
          label="Total revenue"
          value={rupees(summary.total_revenue)}
          sparkline={revenueSeries && revenueSeries.length >= 2 ? revenueSeries : null}
        />
        <StatTile
          label="Recovered via negotiation"
          value={rupees(summary.revenue_recovered_via_negotiation)}
          sub={`${summary.discounted_order_count} discounted orders`}
          accent="emerald"
        />
        <StatTile
          label="Human vs AI-agent revenue"
          value={`${rupees(summary.channel_breakdown.human.revenue)} / ${rupees(summary.channel_breakdown.agent.revenue)}`}
          sub={`${summary.channel_breakdown.human.orders} human - ${summary.channel_breakdown.agent.orders} agent orders`}
        />
        <StatTile label="Negotiations started" value={funnel ? funnel.sessions_started : "N/A"} />
        <StatTile label="Negotiations approved" value={funnel ? funnel.accepted : "N/A"} accent="emerald" />
        <StatTile label="Negotiations rejected" value={funnel ? funnel.rejected : "N/A"} />
        <StatTile label="AI agent orders" value={summary.channel_breakdown.agent.orders} sub="paid orders via buyer-agent channel" />
      </div>
    </CardShell>
  );
}
