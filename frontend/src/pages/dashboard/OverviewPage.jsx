import { Link } from "react-router-dom";
import { useCallback, useState } from "react";

import Card from "../../components/Card.jsx";
import LiveBadge from "../../components/LiveBadge.jsx";
import LiveEventTicker from "../../components/LiveEventTicker.jsx";
import SalesSummaryPanel from "../../components/SalesSummaryPanel.jsx";
import ServiceHealthGrid from "../../components/ServiceHealthGrid.jsx";
import useLiveEvents from "../../hooks/useLiveEvents.js";

// "Merchant Control Center" — a 10-second understanding of the system:
// is it healthy, what's the business shape, what just happened. Every
// heavier technical panel (audit chain, security posture, policy gate
// internals, inventory, policy rules) moved to their own dedicated
// Technical/Analytics sub-pages — this page stays intentionally short.
export default function OverviewPage() {
  const [summaryVersion, setSummaryVersion] = useState(0);
  const onEvent = useCallback((data) => {
    if (data.event_type === "order_created") setSummaryVersion((v) => v + 1);
  }, []);
  const { events, connected } = useLiveEvents(onEvent);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="font-display text-2xl font-semibold text-ink">Merchant Control Center</h1>
        {connected ? <LiveBadge color="emerald" label="Live" /> : <span className="rounded-full bg-putty-light px-2 py-0.5 font-body text-xs font-medium text-ink-soft">connecting...</span>}
      </div>

      <Card title="System Status">
        <ServiceHealthGrid sseConnected={connected} compact />
      </Card>

      <SalesSummaryPanel refreshKey={summaryVersion} />

      <LiveEventTicker events={events} connected={connected} limit={8} />
      <p className="font-body text-xs text-ink-soft/60">
        See <Link to="/dashboard/technical" className="text-clay hover:underline">Technical</Link> for Policy Gate internals,
        the audit chain, AI agent conversations, and the security attack lab — and{" "}
        <Link to="/dashboard/analytics" className="text-clay hover:underline">Analytics</Link> for trends and inventory.
      </p>
    </div>
  );
}
