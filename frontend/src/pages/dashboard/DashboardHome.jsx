import { useEffect, useState } from "react";

import AuditTrailPanel from "../../components/AuditTrailPanel.jsx";
import LiveAgentActivityMap from "../../components/LiveAgentActivityMap.jsx";
import LiveBadge from "../../components/LiveBadge.jsx";
import PolicyGateStatusPanel from "../../components/PolicyGateStatusPanel.jsx";
import RecoverySimulationPanel from "../../components/RecoverySimulationPanel.jsx";
import SalesSummaryPanel from "../../components/SalesSummaryPanel.jsx";
import SecurityPosturePanel from "../../components/SecurityPosturePanel.jsx";
import useDashboardStream from "../../hooks/useDashboardStream.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Stats only, per the dashboard revamp's scope — Human Negotiations and
// AI Buyer Agents now live on their own pages (see DashboardLayout's tab
// bar for how a merchant gets to them).
//
// Phase 17: this page owns the ONE dashboard SSE connection (via
// useDashboardStream) and derives the Live Agent Activity Map's edge
// counts from it directly, rather than LiveAgentActivityMap opening its
// own second connection to the same stream.
export default function DashboardHome() {
  const [summaryVersion, setSummaryVersion] = useState(0);
  const [auditVersion, setAuditVersion] = useState(0);
  const [edgeCounts, setEdgeCounts] = useState({ sellerToGate: 0, buyerToGate: 0 });

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/agent-activity-map`)
      .then((res) => res.json())
      .then((data) =>
        setEdgeCounts({ sellerToGate: data.seller_agent_to_policy_gate, buyerToGate: data.buyer_agent_to_policy_gate })
      )
      .catch(() => {});
  }, []);

  const connected = useDashboardStream((data) => {
    if (data.event_type === "order_created") setSummaryVersion((v) => v + 1);
    if (data.event_type === "gate_decision") setEdgeCounts((c) => ({ ...c, sellerToGate: c.sellerToGate + 1 }));
    if (data.event_type === "agent_negotiate_decided") setEdgeCounts((c) => ({ ...c, buyerToGate: c.buyerToGate + 1 }));
    // Any new audit-log write potentially extends the most-active chain —
    // let the Audit Trail panel refetch so it stays live, not just the
    // sales figures.
    setAuditVersion((v) => v + 1);
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="font-display text-2xl font-semibold text-ink">Merchant Dashboard</h1>
        {connected ? (
          <LiveBadge color="emerald" label="Live" />
        ) : (
          <span className="rounded-full bg-putty-light px-2 py-0.5 font-body text-xs font-medium text-ink-soft">connecting...</span>
        )}
      </div>

      <SalesSummaryPanel refreshKey={summaryVersion} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AuditTrailPanel refreshKey={auditVersion} />
        <div className="space-y-4">
          <PolicyGateStatusPanel />
          <LiveAgentActivityMap sellerToGate={edgeCounts.sellerToGate} buyerToGate={edgeCounts.buyerToGate} />
        </div>
      </div>

      <RecoverySimulationPanel refreshKey={summaryVersion} />
      <SecurityPosturePanel refreshKey={summaryVersion} />
    </div>
  );
}
