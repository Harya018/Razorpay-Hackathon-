import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorBox, SkeletonRows, fmtDate, rupees } from "../components/ui.jsx";
import useAuth from "../hooks/useAuth.js";
import useOrderDetail from "../hooks/useOrderDetail.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Print-friendly invoice. No tax line: this project implements no tax
// calculation, so none is shown — the total is exactly what Razorpay
// charged. Customer details come from the signed-in user's own profile
// (GET /profile); the store name is the storefront's own.
export default function InvoicePage() {
  const { orderId } = useParams();
  const { loading, data, error } = useOrderDetail(orderId);
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/profile`).then((r) => (r.ok ? r.json() : null)).then(setProfile).catch(() => {});
  }, []);

  if (error) return <div className="p-6"><ErrorBox message={error} /></div>;
  if (loading || !data) return <div className="p-6"><SkeletonRows rows={6} /></div>;

  const { summary, payment } = data;
  if (summary.status !== "paid") {
    return (
      <div className="p-6">
        <ErrorBox message="An invoice is only available once payment has been verified." />
        <Link to={`/orders/${orderId}`} className="mt-3 inline-block font-body text-sm text-clay hover:underline">← Back to order</Link>
      </div>
    );
  }
  const p = profile?.profile || {};

  return (
    <div className="p-4 sm:p-6">
      <div className="mb-4 flex items-center gap-3 print:hidden">
        <Link to={`/orders/${orderId}`} className="font-body text-sm text-ink-soft hover:text-ink">← Back to order</Link>
        <button onClick={() => window.print()} className="rounded-sm bg-clay px-4 py-1.5 font-body text-sm font-semibold text-ivory hover:bg-clay-dark">
          Print Invoice
        </button>
      </div>

      <div className="mx-auto max-w-2xl rounded-2xl border border-putty-dark bg-white p-8 shadow-sm print:border-0 print:shadow-none">
        <div className="flex items-start justify-between">
          <div>
            <p className="font-display text-xl font-semibold text-ink">Priya's Shop</p>
            <p className="font-body text-xs text-ink-soft">Bounded Agentic Checkout — Razorpay Test Mode</p>
          </div>
          <div className="text-right">
            <p className="font-body text-[11px] uppercase tracking-wide text-ink-soft">Invoice</p>
            <p className="font-mono text-sm text-ink">{summary.order_ref}</p>
            <p className="font-body text-xs text-ink-soft">Invoice date: {fmtDate(summary.paid_at)}</p>
            <p className="font-body text-xs text-ink-soft">Order date: {fmtDate(summary.created_at)}</p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-4 font-body text-sm">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-ink-soft">Billed to</p>
            <p className="font-medium text-ink">{profile?.name || user?.name || user?.email || "—"}</p>
            <p className="text-ink-soft">{user?.email}</p>
            {p.address_line && <p className="text-ink-soft">{p.address_line}{p.city ? `, ${p.city}` : ""}{p.pincode ? ` ${p.pincode}` : ""}</p>}
            {p.phone && <p className="text-ink-soft">{p.phone}</p>}
          </div>
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-wide text-ink-soft">Payment</p>
            <p className="font-medium text-moss-dark">✓ Paid &amp; verified</p>
            <p className="font-mono text-xs text-ink-soft">{payment.razorpay_payment_id}</p>
          </div>
        </div>

        <table className="mt-6 w-full font-body text-sm">
          <thead>
            <tr className="border-b border-putty-dark text-left text-[11px] uppercase tracking-wide text-ink-soft">
              <th className="py-2">Item</th><th className="py-2 text-right">Qty</th><th className="py-2 text-right">Unit price</th><th className="py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-putty">
              <td className="py-2 text-ink">{summary.product.name} <span className="text-ink-soft/50">#{summary.product.id}</span></td>
              <td className="py-2 text-right">{summary.quantity}</td>
              <td className="py-2 text-right">{rupees(summary.unit_price)}</td>
              <td className="py-2 text-right">{rupees(summary.list_total)}</td>
            </tr>
            {summary.discount > 0 && (
              <tr className="border-b border-putty text-moss-dark">
                <td className="py-2" colSpan={3}>Negotiated discount (Policy Gate approved, {summary.discount_pct}%)</td>
                <td className="py-2 text-right">−{rupees(summary.discount)}</td>
              </tr>
            )}
            <tr>
              <td className="py-3 font-semibold text-ink" colSpan={3}>Total paid</td>
              <td className="py-3 text-right text-base font-bold text-ink">{rupees(summary.amount)}</td>
            </tr>
          </tbody>
        </table>
        <p className="mt-4 font-body text-[11px] text-ink-soft/60">No tax is calculated by this platform. Amount shown is exactly what was charged via Razorpay Test Mode — no real money moved.</p>
      </div>
    </div>
  );
}
