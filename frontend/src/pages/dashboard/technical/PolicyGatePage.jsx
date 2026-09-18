import { useEffect, useState } from "react";

import Card from "../../../components/Card.jsx";
import LiveAgentActivityMap from "../../../components/LiveAgentActivityMap.jsx";
import PolicyGateCard from "../../../components/PolicyGateCard.jsx";
import PolicyGateStatusPanel from "../../../components/PolicyGateStatusPanel.jsx";
import PolicyRulesPanel from "../../../components/PolicyRulesPanel.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Same derivation NegotiationPanel.jsx uses to build a PolicyGateCard from
// real audit events — duplicated here (not imported) since it's a small,
// self-contained 8-line derivation and the two call sites have different
// data-fetching shapes (one live-polls a single open session, this one
// picks the single most recently ACTIVE session across the whole system).
function deriveGateState(events) {
  const lastCall = [...events].reverse().find((e) => e.event_type === "gate_call");
  const lastDecision = [...events].reverse().find((e) => e.event_type === "gate_decision");
  const cartAssessed = events.find((e) => e.event_type === "cart_assessed");
  const catalogPrice = cartAssessed ? cartAssessed.payload.unit_price * cartAssessed.payload.quantity : null;
  if (!lastCall && !lastDecision) return { catalogPrice, decision: null };
  if (!lastDecision || (lastCall && lastCall.id > lastDecision.id)) {
    return { catalogPrice, decision: "pending", requestedValue: lastCall?.payload?.requested_offer?.value ?? null, reason: null, maxAllowed: null };
  }
  return {
    catalogPrice,
    decision: lastDecision.payload.approved ? "approved" : "rejected",
    requestedValue: lastDecision.payload.approved ? lastDecision.payload.final_terms?.value : lastCall?.payload?.requested_offer?.value,
    reason: lastDecision.payload.reason ?? null,
    maxAllowed: lastDecision.payload.max_allowed ?? null,
  };
}

function MostRecentDecision() {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/negotiations?limit=1`)
      .then((res) => res.json())
      .then((sessions) => {
        const session = sessions[0];
        if (!session) return setState({ loading: false, empty: true });
        return fetch(`${API_BASE_URL}/negotiate/${session.session_id}/audit`)
          .then((res) => res.json())
          .then((events) => setState({ loading: false, gate: deriveGateState(events), sessionId: session.session_id }));
      })
      .catch(() => setState({ loading: false, error: true }));
  }, []);

  if (state.loading) return <Card title="Most Recent Decision"><p className="font-body text-sm text-ink-soft">Loading...</p></Card>;
  if (state.empty || state.error || !state.gate?.decision) {
    return (
      <Card title="Most Recent Decision">
        <p className="font-body text-sm text-ink-soft/60">No policy gate decision recorded yet — start a negotiation to see one here.</p>
      </Card>
    );
  }
  return (
    <Card title="Most Recent Decision" note={`Session ${state.sessionId.slice(0, 8)}...`}>
      <PolicyGateCard
        catalogPrice={state.gate.catalogPrice}
        requestedValue={state.gate.requestedValue}
        decision={state.gate.decision}
        reason={state.gate.reason}
        maxAllowed={state.gate.maxAllowed}
      />
    </Card>
  );
}

function EdgeCountMap() {
  const [counts, setCounts] = useState(null);
  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/agent-activity-map`)
      .then((res) => res.json())
      .then((d) => setCounts({ sellerToGate: d.seller_agent_to_policy_gate, buyerToGate: d.buyer_agent_to_policy_gate }))
      .catch(() => {});
  }, []);
  if (!counts) return null;
  return <LiveAgentActivityMap sellerToGate={counts.sellerToGate} buyerToGate={counts.buyerToGate} />;
}

export default function PolicyGatePage() {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-putty-dark bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-display text-lg font-semibold text-ink">Policy Gate</h2>
          <span className="rounded-full bg-moss-light/25 px-2 py-0.5 font-body text-[10px] font-semibold uppercase tracking-wide text-moss-dark">Zero LLM</span>
          <span className="rounded-full bg-moss-light/25 px-2 py-0.5 font-body text-[10px] font-semibold uppercase tracking-wide text-moss-dark">Deterministic</span>
          <span className="rounded-full bg-moss-light/25 px-2 py-0.5 font-body text-[10px] font-semibold uppercase tracking-wide text-moss-dark">Separate service</span>
          <span className="rounded-full bg-moss-light/25 px-2 py-0.5 font-body text-[10px] font-semibold uppercase tracking-wide text-moss-dark">Separate database</span>
        </div>
      </div>

      <PolicyGateStatusPanel />
      <EdgeCountMap />
      <MostRecentDecision />
      <PolicyRulesPanel />
    </div>
  );
}
