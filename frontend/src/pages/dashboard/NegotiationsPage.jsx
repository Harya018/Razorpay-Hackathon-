import { useState } from "react";

import HumanNegotiationFeed from "../../components/HumanNegotiationFeed.jsx";
import useDashboardStream from "../../hooks/useDashboardStream.js";

export default function NegotiationsPage() {
  const [version, setVersion] = useState(0);

  // HumanNegotiationFeed's own header already shows a title + Live badge,
  // so this page doesn't duplicate one — it just owns the version counter
  // that tells the feed when to refetch.
  useDashboardStream((data) => {
    if (data.channel === "human") setVersion((v) => v + 1);
  });

  return <HumanNegotiationFeed refreshKey={version} tall />;
}
