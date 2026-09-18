import Card from "./Card.jsx";
import { Badge, Field, fmtDate, fulfillmentBadge, paymentBadge, rupees } from "./ui.jsx";

// Sections shared by the customer (/orders/:id) and merchant
// (/dashboard/orders/:id) detail pages. Everything rendered is a field the
// backend returned in order_detail.py — nothing is computed here except
// display formatting; the approved price, discount, and verification
// status are the backend's numbers.

export function OrderSummaryCard({ summary, labels }) {
  const [pTone, pLabel] = paymentBadge(summary.status);
  const [fTone, fLabel] = fulfillmentBadge(summary.fulfillment_status, labels);
  return (
    <Card title="Order Summary">
      <div className="flex items-start gap-4">
        {summary.product.image_url && <img src={summary.product.image_url} alt="" className="h-16 w-16 shrink-0 rounded-md border border-putty-dark object-cover" />}
        <div className="min-w-0 flex-1">
          <p className="font-display text-base font-semibold text-ink">{summary.product.name}</p>
          <p className="font-body text-xs text-ink-soft/60">
            Product #{summary.product.id}
            {summary.product.category && ` · ${summary.product.category}`}
            {!summary.product.is_active && " · no longer listed"}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge tone={pTone}>Payment: {pLabel}</Badge>
            <Badge tone={fTone}>{fLabel}</Badge>
            {summary.channel === "agent" && <Badge tone="info">AI buyer agent</Badge>}
          </div>
        </div>
      </div>
      <div className="mt-3 divide-y divide-putty">
        <Field label="Quantity">{summary.quantity}</Field>
        <Field label="Product price">{rupees(summary.unit_price)} × {summary.quantity} = {rupees(summary.list_total)}</Field>
        {summary.discount > 0 ? (
          <>
            <Field label="Negotiated discount">
              <span className="text-moss-dark">−{rupees(summary.discount)} ({summary.discount_pct}%)</span>
            </Field>
            <Field label="Approved price">
              <span className="font-semibold">{rupees(summary.amount)}</span>
            </Field>
          </>
        ) : (
          <Field label="Negotiated discount"><span className="text-ink-soft/50">none — list price</span></Field>
        )}
        <Field label="Final amount"><span className="text-base font-bold">{rupees(summary.amount)}</span></Field>
        <Field label="Order created">{fmtDate(summary.created_at)}</Field>
        {summary.paid_at && <Field label="Paid at">{fmtDate(summary.paid_at)}</Field>}
      </div>
    </Card>
  );
}

export function PaymentCard({ payment }) {
  const [tone, label] = paymentBadge(payment.status);
  return (
    <Card title="Payment" action={<Badge tone="warning">Razorpay Test Mode</Badge>}>
      <div className="divide-y divide-putty">
        <Field label="Status"><Badge tone={tone}>{label}</Badge></Field>
        <Field label="Signature verification">
          {payment.signature_verified ? <span className="text-moss-dark">✓ Verified server-side</span> : <span className="text-ink-soft/60">Not yet verified</span>}
        </Field>
        <Field label="Amount">{rupees(payment.amount)} {payment.currency}</Field>
        <Field label="Razorpay order" mono>{payment.razorpay_order_id}</Field>
        <Field label="Razorpay payment" mono>{payment.razorpay_payment_id || "— (no payment captured yet)"}</Field>
        {payment.verified_at && <Field label="Verified at">{fmtDate(payment.verified_at)} <span className="text-ink-soft/50">via {payment.verification_source}</span></Field>}
        {payment.failed_at && <Field label="Failed at">{fmtDate(payment.failed_at)}</Field>}
      </div>
      <p className="mt-2 font-body text-[11px] text-ink-soft/50">
        "Verified" means the backend independently checked Razorpay's HMAC signature before marking this paid — the
        frontend never asserts it.
      </p>
    </Card>
  );
}

export function PolicyCard({ policy }) {
  if (!policy.negotiated) {
    return (
      <Card title="Policy Gate">
        <p className="font-body text-sm text-ink-soft/70">{policy.note}</p>
      </Card>
    );
  }
  const approved = policy.decision === "approved";
  return (
    <Card title="Policy Gate" action={<Badge tone={approved ? "success" : "error"}>{approved ? "✓ Authorization Verified" : "✕ Rejected"}</Badge>}>
      <div className="divide-y divide-putty">
        <Field label="Requested price (AI proposal)">{rupees(policy.requested_price)}</Field>
        <Field label="Authoritative catalog price">{rupees(policy.authoritative_price)}</Field>
        <Field label="Approved price">{approved ? <span className="font-semibold text-moss-dark">{rupees(policy.approved_price)}</span> : <span className="text-ink-soft/50">none</span>}</Field>
        {approved && <Field label="Discount">{policy.discount_pct}%</Field>}
        {!approved && policy.reason && <Field label="Reason">{policy.reason}</Field>}
        {policy.max_allowed != null && <Field label="Minimum allowed">{rupees(policy.max_allowed)}</Field>}
        <Field label="Approval ID" mono>{policy.approval_ref || "not recorded"}</Field>
        <Field label="Authorized at">{fmtDate(policy.authorized_at)}</Field>
        <Field label="Token redeemed">{policy.redeemed ? `✓ ${fmtDate(policy.redeemed_at)}` : "no"}</Field>
        <Field label="Negotiation session" mono>{policy.session_id?.slice(0, 8)}…</Field>
      </div>
      <p className="mt-2 font-body text-[11px] text-ink-soft/50">
        Decision made deterministically by the separate policy-gate service, which re-fetched the catalog price itself.
        The approval token is single-use and is never displayed.
      </p>
    </Card>
  );
}
