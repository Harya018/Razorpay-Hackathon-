import { Link, useParams } from "react-router-dom";

import Card from "../components/Card.jsx";
import { OrderSummaryCard, PaymentCard, PolicyCard } from "../components/OrderSections.jsx";
import OrderTimeline from "../components/OrderTimeline.jsx";
import OrderTrace from "../components/OrderTrace.jsx";
import { ErrorBox, SkeletonRows } from "../components/ui.jsx";
import useOrderDetail from "../hooks/useOrderDetail.js";

export default function OrderDetailPage() {
  const { orderId } = useParams();
  const { loading, data, error } = useOrderDetail(orderId);

  if (error) return <div className="p-6"><ErrorBox message={error} /><Link to="/orders" className="mt-3 inline-block font-body text-sm text-clay hover:underline">← Back to orders</Link></div>;
  if (loading || !data) return <div className="p-6"><SkeletonRows rows={6} /></div>;

  const { summary, payment, policy, events, trace } = data;

  return (
    <div className="p-4 sm:p-6">
      <Link to="/orders" className="font-body text-sm text-ink-soft hover:text-ink">← Your orders</Link>
      <div className="mb-5 mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-2xl font-semibold text-ink">Order #{summary.order_ref}</h1>
        {summary.status === "paid" && (
          <Link to={`/orders/${summary.order_id}/invoice`} className="rounded-sm border border-clay px-3 py-1.5 font-body text-xs font-medium text-clay hover:bg-putty-light">
            View Invoice
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <OrderSummaryCard summary={summary} labels={data.fulfillment_labels} />
          <Card title="Order Timeline" note="Every ticked step is a real, timestamped audit event for this order. Delivery steps are the platform's own order lifecycle (updated by the merchant), not external courier tracking.">
            <OrderTimeline events={events} fulfillmentStatus={summary.fulfillment_status} fulfillmentSteps={data.fulfillment_steps} fulfillmentLabels={data.fulfillment_labels} />
          </Card>
          <PolicyCard policy={policy} />
        </div>
        <div className="space-y-4">
          <PaymentCard payment={payment} />
          <OrderTrace trace={trace} />
        </div>
      </div>
    </div>
  );
}
