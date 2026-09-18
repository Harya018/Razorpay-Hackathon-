import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Empty, ErrorBox, SkeletonRows, fmtDate, fulfillmentBadge, paymentBadge, readError, rupees } from "../components/ui.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const LABELS = { placed: "Order Placed", processing: "Processing", shipped: "Shipped", out_for_delivery: "Out for Delivery", delivered: "Delivered" };

export default function OrdersPage() {
  const [orders, setOrders] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/orders`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await readError(res, "Couldn't load your orders"));
        return res.json();
      })
      .then(setOrders)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="p-4 sm:p-6">
      <h1 className="font-display text-2xl font-semibold text-ink">Your Orders</h1>
      <p className="mb-5 mt-1 font-body text-sm text-ink-soft">Every order placed while signed in to this account.</p>

      {error && <ErrorBox message={error} />}
      {!orders && !error && <SkeletonRows rows={3} />}
      {orders && orders.length === 0 && <Empty title="No orders yet" body="Orders you place while signed in will appear here." />}

      {orders && orders.length > 0 && (
        <ul className="space-y-3">
          {orders.map((o) => {
            const [pTone, pLabel] = paymentBadge(o.status);
            const [fTone, fLabel] = fulfillmentBadge(o.fulfillment_status, LABELS);
            return (
              <li key={o.order_id} className="flex flex-wrap items-center gap-4 rounded-md border border-putty-dark bg-ivory p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-xs text-ink-soft/60">{o.order_ref}</p>
                  <p className="font-body text-sm font-medium text-ink">{o.product_name} × {o.quantity}</p>
                  <p className="font-body text-xs text-ink-soft/70">{fmtDate(o.created_at)}</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <p className="font-body text-base font-bold text-ink">{rupees(o.amount)}</p>
                  <div className="flex gap-1.5"><Badge tone={pTone}>{pLabel}</Badge><Badge tone={fTone}>{fLabel}</Badge></div>
                </div>
                <Link to={`/orders/${o.order_id}`} className="rounded-sm border border-clay px-3 py-1.5 font-body text-xs font-medium text-clay hover:bg-putty-light">
                  View Order
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
