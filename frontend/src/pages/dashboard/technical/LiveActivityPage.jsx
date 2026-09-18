import { useCallback, useState } from "react";

import HumanNegotiationFeed from "../../../components/HumanNegotiationFeed.jsx";
import LiveEventTicker from "../../../components/LiveEventTicker.jsx";
import useLiveEvents from "../../../hooks/useLiveEvents.js";

// Owns this page's single SSE connection: the ticker gets the raw buffer,
// and every human-channel event bumps the negotiation feed's refreshKey
// so it refetches live (same behavior the old standalone NegotiationsPage
// had — a feed with no refreshKey would only ever load once on mount).
export default function LiveActivityPage() {
  const [feedVersion, setFeedVersion] = useState(0);
  const onEvent = useCallback((data) => {
    if (data.channel === "human") setFeedVersion((v) => v + 1);
  }, []);
  const { events, connected } = useLiveEvents(onEvent);

  return (
    <div className="space-y-4">
      <LiveEventTicker events={events} connected={connected} limit={15} />
      <HumanNegotiationFeed refreshKey={feedVersion} tall />
    </div>
  );
}
