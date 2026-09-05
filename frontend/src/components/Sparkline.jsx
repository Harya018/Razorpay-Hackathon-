// Tiny inline trend line for a stat card. ONLY ever passed a `points`
// array that came from a real, already-computed time series (e.g.
// GET /dashboard/analytics's revenue_over_time) — never invented data.
// If a stat has no backing series, don't render this at all rather than
// pass it a single point or a fake trend.
export default function Sparkline({ points, width = 96, height = 28, color = "#8b6552" }) {
  if (!points || points.length < 2) return null;

  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const range = max - min || 1;
  const stepX = width / (points.length - 1);
  const coords = points.map((v, i) => [i * stepX, height - ((v - min) / range) * (height - 4) - 2]);
  const path = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");

  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={coords[coords.length - 1][0]} cy={coords[coords.length - 1][1]} r="2" fill={color} />
    </svg>
  );
}
