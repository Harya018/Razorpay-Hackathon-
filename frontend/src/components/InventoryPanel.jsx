import { useEffect, useState } from "react";

import Card from "./Card.jsx";
import StockBadge from "./StockBadge.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Section 13's inventory overview — every row comes straight from the
// real /catalog response (id, price, stock — nothing fabricated), joined
// against /dashboard/analytics's already-real negotiation-frequency and
// revenue-by-product breakdowns for the "Negotiations"/"Sales" columns.
// No maximum-capacity bar is shown — this backend has no stock-capacity
// concept, only a current quantity, so a "X/Y, 60%" bar would be invented.
export default function InventoryPanel({ refreshKey }) {
  const [products, setProducts] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/catalog`).then((res) => (res.ok ? res.json() : Promise.reject(new Error("Failed to load catalog")))),
      fetch(`${API_BASE_URL}/dashboard/analytics`).then((res) => (res.ok ? res.json() : null)),
    ])
      .then(([catalog, analyticsData]) => {
        setProducts(catalog);
        setAnalytics(analyticsData);
      })
      .catch((err) => setError(err.message));
  }, [refreshKey]);

  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;
  if (!products) return <p className="font-body text-sm text-ink-soft">Loading inventory...</p>;

  const negotiationsByName = new Map((analytics?.top_products_by_negotiation_frequency ?? []).map((r) => [r.name, r.session_count]));
  const salesByName = new Map((analytics?.top_products_by_revenue ?? []).map((r) => [r.name, r.orders]));

  return (
    <Card title="Inventory" note="Real stock quantities from the catalog — no fabricated capacity or forecast numbers.">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] font-body text-sm">
          <thead>
            <tr className="border-b border-putty-dark text-left text-[11px] font-semibold uppercase tracking-wide text-ink-soft/70">
              <th className="py-2 pr-2">Product</th>
              <th className="py-2 pr-2">ID</th>
              <th className="py-2 pr-2">Catalog price</th>
              <th className="py-2 pr-2">Status</th>
              <th className="py-2 pr-2">Negotiations</th>
              <th className="py-2">Sales</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id} className="border-b border-putty-dark/60 last:border-b-0">
                <td className="max-w-[220px] truncate py-2 pr-2 font-medium text-ink">{p.name}</td>
                <td className="py-2 pr-2 text-ink-soft/70">#{p.id}</td>
                <td className="py-2 pr-2 text-ink">₹{(p.price / 100).toFixed(2)}</td>
                <td className="py-2 pr-2"><StockBadge stock={p.stock} /></td>
                <td className="py-2 pr-2 text-ink-soft">{negotiationsByName.get(p.name) ?? 0}</td>
                <td className="py-2 text-ink-soft">{salesByName.get(p.name) ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
