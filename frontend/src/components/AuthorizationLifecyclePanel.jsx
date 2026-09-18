import { useEffect, useMemo, useState } from "react";

import Card from "./Card.jsx";
import { rupees } from "../utils/eventTranslation.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Turns the real audit-log events for one negotiation (and, once an order
// exists, that order's own events too) into the step-by-step lifecycle:
// offer -> policy evaluation -> authorization -> acceptance -> token
// redemption -> Razorpay order -> payment confirmation. Every step is
// derived from a REAL event this session actually produced; a step with
// no matching event renders as "Not reached yet" rather than a guess.
//
// Two real events (gate_call+gate_decision) are DELIBERATELY merged into
// one "Policy Evaluated" step, and price re-verification is called out as
// part of that same step rather than invented as its own timestamped
// entry — the backend performs price re-verification INSIDE the same
// /evaluate call, it is not a separately logged event (confirmed by
// reading policy-gate/app/routes/evaluate.py and backend's audit writes).
function buildSteps(sessionEvents, orderEvents) {
  const byType = (t) => sessionEvents.find((e) => e.event_type === t);
  const offerProposed = byType("offer_proposed");
  const gateCall = byType("gate_call");
  const gateDecision = byType("gate_decision");
  const closed = byType("negotiation_closed");
  const orderCreated = byType("order_created") || orderEvents.find((e) => e.event_type === "order_created");
  const paymentConfirmed = orderEvents.find((e) => e.event_type === "order_confirmed_client_side");

  const approved = gateDecision?.payload?.approved === true;
  const accepted = closed?.payload?.final_status === "accepted";

  return [
    {
      key: "offer_proposed",
      label: "Offer Proposed",
      sub: "By the seller LLM — a proposal, not yet an authorization",
      event: offerProposed,
      detail: offerProposed ? `${offerProposed.payload.type} at ${rupees(offerProposed.payload.value)}` : null,
    },
    {
      key: "policy_evaluated",
      label: "Policy Evaluated",
      sub: "Deterministic — includes an independent catalog price re-verification inside the same /evaluate call",
      event: gateDecision || gateCall,
      detail: gateDecision ? (approved ? "Approved" : `Rejected — ${gateDecision.payload.reason || "policy violation"}`) : gateCall ? "Sent to Policy Gate, awaiting decision" : null,
    },
    {
      key: "token_issued",
      label: "Approval Token Issued",
      sub: "Single-use — the token value itself is never logged or exposed by any API",
      event: approved ? gateDecision : null,
      detail: approved ? `Authorized amount ${rupees(gateDecision.payload.final_terms?.value)}` : accepted === false && closed ? "Not issued — offer was not approved" : null,
    },
    {
      key: "customer_accepted",
      label: "Customer Accepted",
      sub: "A human reply, interpreted deterministically by the graph's transition logic — not an LLM discretionary call",
      event: accepted ? closed : null,
      detail: accepted ? `After ${closed.payload.turns} turn(s)` : null,
    },
    {
      key: "token_redeemed",
      label: "Token Verified & Redeemed",
      sub: "policy-gate's /verify re-checks the token against its own record and atomically marks it used",
      event: orderCreated?.payload?.discount_applied ? orderCreated : null,
      detail: orderCreated?.payload?.discount_applied ? "Verified — discount applied" : null,
    },
    {
      key: "order_created",
      label: "Razorpay Order Created",
      sub: "Test Mode — amount comes from the redeemed token's terms, never a client-supplied value",
      event: orderCreated,
      detail: orderCreated ? `Order #${orderCreated.order_id ?? "—"} — ${rupees(orderCreated.payload.amount)}` : null,
    },
    {
      key: "payment_confirmed",
      label: "Payment Confirmed",
      sub: "Razorpay signature independently verified server-side before status becomes \"paid\"",
      event: paymentConfirmed,
      detail: paymentConfirmed ? "Signature verified" : null,
    },
  ];
}

export default function AuthorizationLifecyclePanel() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [sessionEvents, setSessionEvents] = useState([]);
  const [orderEvents, setOrderEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/negotiations?limit=20`)
      .then((res) => res.json())
      .then((data) => {
        setSessions(data);
        const preferred = data.find((s) => s.final_status === "accepted") || data[0];
        setSessionId(preferred?.session_id ?? null);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    fetch(`${API_BASE_URL}/negotiate/${sessionId}/audit`)
      .then((res) => res.json())
      .then(async (events) => {
        setSessionEvents(events);
        const orderCreated = events.find((e) => e.event_type === "order_created");
        if (orderCreated?.order_id) {
          const orderRes = await fetch(`${API_BASE_URL}/order/${orderCreated.order_id}/audit`);
          setOrderEvents(orderRes.ok ? await orderRes.json() : []);
        } else {
          setOrderEvents([]);
        }
      })
      .catch(() => {});
  }, [sessionId]);

  const steps = useMemo(() => buildSteps(sessionEvents, orderEvents), [sessionEvents, orderEvents]);

  if (loading) return <Card title="Authorization Lifecycle"><p className="font-body text-sm text-ink-soft">Loading...</p></Card>;
  if (sessions.length === 0) {
    return (
      <Card title="Authorization Lifecycle">
        <p className="font-body text-sm text-ink-soft/70">No negotiation sessions recorded yet.</p>
      </Card>
    );
  }

  return (
    <Card title="Authorization Lifecycle" note="Every step below is a real audit event from the session selected — no step is fabricated.">
      <label className="mb-3 flex items-center gap-2 font-body text-xs text-ink-soft">
        Session:
        <select
          value={sessionId ?? ""}
          onChange={(e) => setSessionId(e.target.value)}
          className="rounded-sm border border-putty-dark bg-ivory px-2 py-1 font-mono text-[11px] text-ink"
        >
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.session_id.slice(0, 8)} — {s.headline}
            </option>
          ))}
        </select>
      </label>

      <ol className="space-y-0">
        {steps.map((step, i) => {
          const reached = Boolean(step.event);
          return (
            <li key={step.key} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                    reached ? "bg-moss text-ivory" : "bg-putty-light text-ink-soft/50"
                  }`}
                >
                  {reached ? "✓" : i + 1}
                </span>
                {i < steps.length - 1 && <span className={`w-px flex-1 ${reached ? "bg-moss-light" : "bg-putty"}`} style={{ minHeight: "1.75rem" }} />}
              </div>
              <div className="min-w-0 flex-1 pb-4">
                <p className={`font-body text-sm font-semibold ${reached ? "text-ink" : "text-ink-soft/50"}`}>{step.label}</p>
                <p className="font-body text-[11px] text-ink-soft/60">{step.sub}</p>
                {reached ? (
                  <p className="mt-0.5 font-body text-xs text-moss-dark">
                    {step.detail} — <span className="text-ink-soft/50">{new Date(step.event.created_at).toLocaleTimeString()}</span>
                  </p>
                ) : (
                  <p className="mt-0.5 font-body text-xs text-ink-soft/40">Not reached yet</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
