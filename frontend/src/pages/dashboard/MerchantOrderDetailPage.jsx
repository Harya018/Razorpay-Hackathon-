import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import Card from "../../components/Card.jsx";
import { OrderSummaryCard, PaymentCard, PolicyCard } from "../../components/OrderSections.jsx";
import OrderTimeline from "../../components/OrderTimeline.jsx";
import OrderTrace from "../../components/OrderTrace.jsx";
import { Badge, ErrorBox, Field, SkeletonRows, fmtDate, readError } from "../../components/ui.jsx";
import useOrderDetail from "../../hooks/useOrderDetail.js";
import { toastError, toastSuccess } from "../../lib/toast.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function EventRow({ e }) {
  const [raw, setRaw] = useState(false);
  return (
    <li className="border-b border-putty-dark/60 py-2 last:border-b-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-[11px]">
        <span className="text-ink-soft/60">{new Date(e.created_at).toLocaleTimeString()}</span>
        <span className="font-semibold text-ink">{e.event_type}</span>
        <Badge tone="neutral">{e.actor}</Badge>
        <span className="text-ink-soft">{e.summary}</span>
        <span className="text-ink-soft/50">hash {e.entry_hash_short}</span>
        <button onClick={() => setRaw((r) => !r)} className="ml-auto text-clay hover:underline">{raw ? "Hide raw" : "View Raw Event"}</button>
      </div>
      {raw && <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded border border-putty-dark bg-ivory p-2 font-mono text-[11px] text-ink-soft">{JSON.stringify(e.payload, null, 2)}</pre>}
    </li>
  );
}

export default function MerchantOrderDetailPage() {
  const { orderId } = useParams();
  const { loading, data, error, reload } = useOrderDetail(orderId, { merchant: true });
  const [busy, setBusy] = useState(false);

  if (error) return <div><ErrorBox message={error} /><Link to="/dashboard/orders" className="mt-3 inline-block font-body text-sm text-clay hover:underline">← Orders</Link></div>;
  if (loading || !data) return <SkeletonRows rows={8} />;

  const { summary, payment, policy, events, trace, customer, fulfillment_steps: steps, fulfillment_labels: labels } = data;
  const currentIdx = summary.fulfillment_status ? steps.indexOf(summary.fulfillment_status) : -1;
  const nextStep = summary.status === "paid" && currentIdx < steps.length - 1 ? steps[currentIdx + 1] : null;

  async function advance() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE_URL}/dashboard/orders/${summary.order_id}/status`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: nextStep }) });
      if (!res.ok) throw new Error(await readError(res, "Couldn't update order status"));
      toastSuccess(`${summary.order_ref} → ${labels[nextStep]}`);
      reload();
    } catch (err) {
      toastError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Link to="/dashboard/orders" className="font-body text-sm text-ink-soft hover:text-ink">← Orders</Link>
      <div className="mb-5 mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-2xl font-semibold text-ink">Order #{summary.order_ref}</h1>
        {nextStep ? (
          <button onClick={advance} disabled={busy} className="rounded-lg bg-clay px-4 py-2 font-body text-sm font-semibold text-ivory hover:bg-clay-dark disabled:opacity-60">
            {busy ? "Updating…" : `Mark as ${labels[nextStep]}`}
          </button>
        ) : summary.status === "paid" ? (
          <Badge tone="success">Delivered — lifecycle complete</Badge>
        ) : (
          <Badge tone="neutral">Lifecycle starts once paid</Badge>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <OrderSummaryCard summary={summary} labels={labels} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <PaymentCard payment={payment} />
            <Card title="Customer">
              {customer.note && <p className="mb-2 font-body text-xs text-ink-soft/60">{customer.note}</p>}
              <div className="divide-y divide-putty">
                <Field label="Name">{customer.name || <span className="text-ink-soft/40">not set</span>}</Field>
                <Field label="Email">{customer.email || "—"}</Field>
                <Field label="User ID" mono>{customer.user_id || "—"}</Field>
                <Field label="Phone">{customer.phone || <span className="text-ink-soft/40">not provided</span>}</Field>
                <Field label="Shipping">{customer.address_line ? `${customer.address_line}, ${customer.city || ""} ${customer.pincode || ""}` : <span className="text-ink-soft/40">not provided</span>}</Field>
              </div>
            </Card>
          </div>
          <PolicyCard policy={policy} />
          <Card title="Audit Trail" note={`${events.length} hash-chained events for this order and its negotiation session, chronological.`}>
            <ul>{events.map((e) => <EventRow key={e.id} e={e} />)}</ul>
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Timeline">
            <OrderTimeline events={events} fulfillmentStatus={summary.fulfillment_status} fulfillmentSteps={steps} fulfillmentLabels={labels} />
          </Card>
          <OrderTrace trace={trace} />
          <Card title="Webhook">
            <p className="font-body text-xs text-ink-soft/70">{payment.webhook_status} — see Technical → Payments for the verified-delivery log by Razorpay event id.</p>
            <p className="mt-1 font-body text-[11px] text-ink-soft/50">Order updated {fmtDate(summary.updated_at)}</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
