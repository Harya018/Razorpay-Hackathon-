import Card from "./Card.jsx";

// Per the project's own data-integrity rule: the backend doesn't expose
// per-request idempotency state via any API (confirmed — no GET endpoint
// reads IdempotencyRecord), so this card states the real, implemented
// server-side behavior honestly rather than fabricating a live dashboard
// for data that isn't queryable.
export default function IdempotencyCard() {
  return (
    <Card title="Request Safety — Idempotency">
      <div className="space-y-2 font-body text-sm">
        <div className="flex items-center justify-between">
          <span className="text-ink-soft">POST /negotiate/start</span>
          <span className="font-medium text-moss-dark">✓ Enabled (database-backed)</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-ink-soft">POST /order/create</span>
          <span className="font-medium text-moss-dark">✓ Enabled (Order.idempotency_key)</span>
        </div>
      </div>
      <p className="mt-3 font-body text-xs text-ink-soft/70">
        A repeated request carrying the same <code className="rounded bg-putty-light px-1 font-mono">Idempotency-Key</code> header
        returns the SAME session/order instead of creating a duplicate — verified by
        <code className="ml-1 rounded bg-putty-light px-1 font-mono">backend/tests/test_idempotency.py</code>.
      </p>
      <p className="mt-2 font-body text-[11px] text-ink-soft/50">
        Implemented server-side; detailed per-request state is not exposed by any current API, so this card describes the
        real mechanism rather than a live feed.
      </p>
    </Card>
  );
}
