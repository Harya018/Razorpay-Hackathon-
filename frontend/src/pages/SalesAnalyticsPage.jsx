import { useEffect, useState } from "react";

import CardShell from "../components/Card.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Small, dependency-free SVG charts — this project avoids hotlinked/
// external services wherever a self-contained alternative works (see
// seed_catalog.py's own note on why placeholder images are generated
// in-process rather than fetched), and no charting library is installed
// here yet; hand-rolled SVG keeps the bundle small. Phase 19: colors
// moved to the storefront's warm clay/moss family to match the light
// card rebuild — the chart MATH (padding, scaling, point layout) is
// byte-for-byte unchanged from before the restyle.

function LineChart({ points, height = 160, formatValue }) {
  if (!points.length) return <p className="font-body text-xs text-ink-soft/70">No data yet.</p>;
  // Padding on every side: the value label sits ABOVE each point and the
  // date label BELOW the plot area, and centered text at x=0 or y=0 spills
  // outside the SVG's own box — real bugs caught by actually looking at
  // rendered screenshots (the leftmost point's label half off-canvas at
  // x=0, then the tallest point's value label clipped above y=0), not
  // assumed away. padTop leaves room for the highest point's value label;
  // padX does the same for the first/last point's labels horizontally.
  const padX = 32;
  const padTop = 16;
  const padBottom = 16;
  const plotWidth = Math.max((points.length - 1) * 70, 220);
  const plotHeight = height;
  const width = plotWidth + padX * 2;
  const svgHeight = padTop + plotHeight + padBottom;
  const max = Math.max(...points.map((p) => p.value), 1);
  const stepX = plotWidth / Math.max(points.length - 1, 1);
  const coords = points.map((p, i) => [padX + i * stepX, padTop + plotHeight - (p.value / max) * plotHeight]);
  const path = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
  const baseline = padTop + plotHeight;
  const area = `${path} L ${coords[coords.length - 1][0]} ${baseline} L ${padX} ${baseline} Z`;

  return (
    <div className="overflow-x-auto">
      <svg width={width} height={svgHeight} className="min-w-full">
        <path d={area} fill="rgba(139,101,82,0.12)" />
        <path d={path} fill="none" stroke="#8b6552" strokeWidth="2" />
        {coords.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="3" fill="#8b6552" />
        ))}
        {points.map((p, i) => (
          <text key={i} x={coords[i][0]} y={baseline + 14} textAnchor="middle" fontSize="9.5" fontFamily="inherit" fill="#a98977">
            {p.label}
          </text>
        ))}
        {coords.map(([x, y], i) => (
          <text key={`v-${i}`} x={x} y={Math.max(y - 8, 9)} textAnchor="middle" fontSize="9.5" fontFamily="inherit" fill="#5c574c">
            {formatValue ? formatValue(points[i].value) : points[i].value}
          </text>
        ))}
      </svg>
    </div>
  );
}

function StackedBarChart({ points, height = 160 }) {
  if (!points.length) return <p className="font-body text-xs text-ink-soft/70">No data yet.</p>;
  const width = Math.max(points.length * 70, 280);
  const max = Math.max(...points.map((p) => p.human + p.agent), 1);
  const barWidth = Math.min(36, (width / points.length) * 0.6);

  return (
    <div className="overflow-x-auto">
      <svg width={width} height={height + 24} className="min-w-full">
        {points.map((p, i) => {
          const stepX = width / points.length;
          const x = i * stepX + stepX / 2 - barWidth / 2;
          const humanH = (p.human / max) * (height - 12);
          const agentH = (p.agent / max) * (height - 12);
          return (
            <g key={i}>
              <rect x={x} y={height - humanH - agentH} width={barWidth} height={agentH} fill="#7c3aed" rx="2" />
              <rect x={x} y={height - humanH} width={barWidth} height={humanH} fill="#8b6552" rx="2" />
              <text x={x + barWidth / 2} y={height + 16} textAnchor="middle" fontSize="9.5" fontFamily="inherit" fill="#a98977">
                {p.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex gap-4 font-body text-[10px] text-ink-soft/70">
        <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#8b6552]" /> human</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#7c3aed]" /> agent</span>
      </div>
    </div>
  );
}

function FunnelBar({ label, value, max, accent = "bg-clay" }) {
  const pct = max ? Math.round((value / max) * 100) : 0;
  return (
    <div className="mb-2">
      <div className="mb-0.5 flex items-baseline justify-between font-body text-[11px]">
        <span className="text-ink-soft">{label}</span>
        <span className="font-semibold text-ink">
          {value} <span className="font-normal text-ink-soft/60">({pct}%)</span>
        </span>
      </div>
      <div className="h-3 w-full rounded-full bg-putty-light">
        <div className={`h-full rounded-full ${accent}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function SalesAnalyticsPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/analytics`)
      .then((res) => res.json())
      .then(setData)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="min-h-screen bg-ivory p-4 sm:p-6">
      <h1 className="mb-1 font-display text-2xl font-semibold text-ink">Sales Analytics</h1>
      {/* Framing text — unchanged wording, kept as the first line under
          the title, same as before the restyle. */}
      <p className="mb-5 font-body text-sm text-ink-soft">
        Trends, not live events — see Merchant Dashboard for real-time activity. All figures below are computed from
        real order/negotiation history unless explicitly marked simulated.
      </p>

      {error && <p className="font-body text-sm text-rose-700">{error}</p>}
      {!data && !error && <p className="font-body text-sm text-ink-soft">Loading analytics...</p>}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <CardShell title="Revenue Over Time" note={`Real orders, bucketed by ${data.granularity}.`}>
              <LineChart
                points={data.revenue_over_time.map((r) => ({ label: r.bucket.slice(5), value: r.revenue }))}
                formatValue={(v) => `₹${Math.round(v)}`}
              />
            </CardShell>

            <CardShell title="Human vs AI-Agent Revenue Over Time" note="Real orders, split by channel.">
              <StackedBarChart
                points={data.channel_revenue_over_time.map((r) => ({
                  label: r.bucket.slice(5),
                  human: r.human_revenue,
                  agent: r.agent_revenue,
                }))}
              />
            </CardShell>
          </div>

          <CardShell
            title="Negotiation Funnel"
            note="Real human-negotiation sessions from the audit log — not simulated."
          >
            <FunnelBar label="Sessions started" value={data.negotiation_funnel.sessions_started} max={data.negotiation_funnel.sessions_started} accent="bg-clay" />
            <FunnelBar label="Offer extended" value={data.negotiation_funnel.offers_extended} max={data.negotiation_funnel.sessions_started} accent="bg-clay" />
            <FunnelBar label="Accepted" value={data.negotiation_funnel.accepted} max={data.negotiation_funnel.sessions_started} accent="bg-moss" />
            <FunnelBar label="Rejected" value={data.negotiation_funnel.rejected} max={data.negotiation_funnel.sessions_started} accent="bg-rose-500" />
            <FunnelBar label="Abandoned / no decision recorded" value={data.negotiation_funnel.abandoned} max={data.negotiation_funnel.sessions_started} accent="bg-putty-dark" />
            <p className="mt-2 font-body text-[10px] text-ink-soft/70">{data.negotiation_funnel.note}</p>
          </CardShell>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <CardShell
              title="Discount Tier Breakdown (Real)"
              note="Which rung actually closed real sales — NOT the Revenue Recovery (Simulated) card on the Overview tab."
            >
              {Object.keys(data.discount_tier_breakdown_real).length === 0 ? (
                <p className="font-body text-xs text-ink-soft/70">No accepted negotiations yet.</p>
              ) : (
                Object.entries(data.discount_tier_breakdown_real).map(([tier, count]) => (
                  <FunnelBar
                    key={tier}
                    label={tier}
                    value={count}
                    max={Math.max(...Object.values(data.discount_tier_breakdown_real))}
                    accent="bg-amber-500"
                  />
                ))
              )}
            </CardShell>

            <CardShell title="Top Products by Revenue" note="Real orders.">
              <table className="w-full font-mono text-[11px]">
                <tbody>
                  {data.top_products_by_revenue.map((p) => (
                    <tr key={p.product_id} className="border-b border-putty-light last:border-0">
                      <td className="py-1.5 pr-2 text-ink">{p.name}</td>
                      <td className="py-1.5 pr-2 text-right text-ink-soft/60">{p.orders} orders</td>
                      <td className="py-1.5 text-right font-semibold text-ink">₹{p.revenue.toLocaleString("en-IN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardShell>
          </div>

          <CardShell title="Top Products by Negotiation Frequency" note="Real negotiation sessions started, by product.">
            <table className="w-full font-mono text-[11px]">
              <tbody>
                {data.top_products_by_negotiation_frequency.map((p) => (
                  <tr key={p.name} className="border-b border-putty-light last:border-0">
                    <td className="py-1.5 pr-2 text-ink">{p.name}</td>
                    <td className="py-1.5 text-right font-semibold text-ink">{p.session_count} sessions</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardShell>
        </div>
      )}
    </div>
  );
}
