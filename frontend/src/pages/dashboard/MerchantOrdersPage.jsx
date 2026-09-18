import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import Card from "../../components/Card.jsx";
import { Badge, Empty, ErrorBox, SkeletonRows, fmtDate, fulfillmentBadge, paymentBadge, readError, rupees } from "../../components/ui.jsx";
import useDashboardStream from "../../hooks/useDashboardStream.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const LABELS = { placed: "Order Placed", processing: "Processing", shipped: "Shipped", out_for_delivery: "Out for Delivery", delivered: "Delivered" };
const FILTERS = [["", "All"], ["paid", "Paid"], ["created", "Pending"], ["failed", "Failed"]];

export default function MerchantOrdersPage() {
  const [orders, setOrders] = useState(null);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("");
  const [version, setVersion] = useState(0);

  // Live: any order/payment audit write refreshes the list (SSE, no polling).
  useDashboardStream((e) => {
    if (e.order_id || ["order_created", "payment_verified", "payment_failed", "order_status_updated"].includes(e.event_type)) setVersion((v) => v + 1);
  });

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/orders${status ? `?status=${status}` : ""}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await readError(res, "Couldn't load orders"));
        return res.json();
      })
      .then(setOrders)
      .catch((err) => setError(err.message));
  }, [status, version]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-ink">Orders</h1>
          <p className="font-body text-sm text-ink-soft">Every order the backend has created, live-updated from the audit stream.</p>
        </div>
        <div className="inline-flex gap-1 rounded-lg border border-putty-dark bg-white p-1">
          {FILTERS.map(([v, label]) => (
            <button key={v} onClick={() => setStatus(v)} className={`rounded-md px-3 py-1 font-body text-xs font-medium ${status === v ? "bg-ink text-ivory" : "text-ink-soft hover:bg-putty-light"}`}>{label}</button>
          ))}
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      <Card>
        {!orders && !error && <SkeletonRows rows={8} />}
        {orders && orders.length === 0 && <Empty title="No orders" body="Completed orders will appear here." />}
        {orders && orders.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] font-body text-sm">
              <thead>
                <tr className="border-b border-putty-dark text-left text-[11px] font-semibold uppercase tracking-wide text-ink-soft/70">
                  <th className="py-2 pr-2">Order</th><th className="py-2 pr-2">Customer</th><th className="py-2 pr-2">Product</th><th className="py-2 pr-2">Amount</th>
                  <th className="py-2 pr-2">Payment</th><th className="py-2 pr-2">Order status</th><th className="py-2 pr-2">Created</th><th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => {
                  const [pTone, pLabel] = paymentBadge(o.status);
                  const [fTone, fLabel] = fulfillmentBadge(o.fulfillment_status, LABELS);
                  return (
                    <tr key={o.order_id} className="border-b border-putty-dark/60 last:border-b-0">
                      <td className="py-2 pr-2 font-mono text-xs text-ink">{o.order_ref}</td>
                      <td className="max-w-[180px] truncate py-2 pr-2 text-ink-soft">{o.customer_email || (o.buyer_agent_id ? <Badge tone="info">{o.buyer_agent_id}</Badge> : <span className="text-ink-soft/50">guest</span>)}</td>
                      <td className="max-w-[220px] truncate py-2 pr-2 text-ink">{o.product_name} × {o.quantity}</td>
                      <td className="py-2 pr-2 font-medium text-ink">{rupees(o.amount)}</td>
                      <td className="py-2 pr-2"><Badge tone={pTone}>{pLabel}</Badge></td>
                      <td className="py-2 pr-2"><Badge tone={fTone}>{fLabel}</Badge></td>
                      <td className="py-2 pr-2 text-xs text-ink-soft/70">{fmtDate(o.created_at)}</td>
                      <td className="py-2"><Link to={`/dashboard/orders/${o.order_id}`} className="rounded-sm border border-clay px-2.5 py-1 font-body text-xs font-medium text-clay hover:bg-putty-light">View Details</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
