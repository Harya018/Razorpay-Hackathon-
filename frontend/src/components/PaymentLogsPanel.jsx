import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import Card from "./Card.jsx";
import { Badge, Empty, ErrorBox, SkeletonRows, fmtDate, readError, rupees } from "./ui.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const FILTERS = [["all", "All"], ["successful", "Successful"], ["failed", "Failed"], ["pending", "Pending"]];

// GET /dashboard/payments — real payment-related audit events joined to
// their order rows. The filter is by the order's authoritative status.
export default function PaymentLogsPanel() {
  const [outcome, setOutcome] = useState("all");
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setRows(null);
    fetch(`${API_BASE_URL}/dashboard/payments?outcome=${outcome}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await readError(res, "Couldn't load payment logs"));
        return res.json();
      })
      .then(setRows)
      .catch((err) => setError(err.message));
  }, [outcome]);

  return (
    <Card
      title="Payment Logs"
      note="Real audit events (order_created, payment_verified, payment_failed, …) joined to their order — filter is by the order's current status."
      action={
        <div className="inline-flex gap-1 rounded-lg border border-putty-dark bg-white p-0.5">
          {FILTERS.map(([v, label]) => (
            <button key={v} onClick={() => setOutcome(v)} className={`rounded-md px-2 py-0.5 font-body text-[11px] font-medium ${outcome === v ? "bg-ink text-ivory" : "text-ink-soft hover:bg-putty-light"}`}>{label}</button>
          ))}
        </div>
      }
    >
      {error && <ErrorBox message={error} />}
      {!rows && !error && <SkeletonRows rows={5} />}
      {rows && rows.length === 0 && <Empty title="No payment events" body="Nothing matches this filter yet." />}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] font-body text-sm">
            <thead>
              <tr className="border-b border-putty-dark text-left text-[11px] font-semibold uppercase tracking-wide text-ink-soft/70">
                <th className="py-2 pr-2">Time</th><th className="py-2 pr-2">Order</th><th className="py-2 pr-2">Razorpay order</th><th className="py-2 pr-2">Razorpay payment</th>
                <th className="py-2 pr-2">Amount</th><th className="py-2 pr-2">Event</th><th className="py-2 pr-2">Verified</th><th className="py-2">Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-putty-dark/60 last:border-b-0">
                  <td className="py-2 pr-2 text-xs text-ink-soft/70">{fmtDate(r.timestamp)}</td>
                  <td className="py-2 pr-2 font-mono text-xs">{r.order_id ? <Link to={`/dashboard/orders/${r.order_id}`} className="text-clay hover:underline">{r.order_ref}</Link> : "—"}</td>
                  <td className="py-2 pr-2 font-mono text-xs text-ink-soft">{r.razorpay_order_id || "—"}</td>
                  <td className="py-2 pr-2 font-mono text-xs text-ink-soft">{r.razorpay_payment_id || "—"}</td>
                  <td className="py-2 pr-2 text-ink">{rupees(r.amount)}</td>
                  <td className="py-2 pr-2 font-mono text-xs text-ink">{r.event}</td>
                  <td className="py-2 pr-2">{r.verified ? <Badge tone="success">✓ Verified</Badge> : <Badge tone={r.order_status === "failed" ? "error" : "warning"}>{r.order_status || "—"}</Badge>}</td>
                  <td className="py-2 text-xs text-ink-soft">{r.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
