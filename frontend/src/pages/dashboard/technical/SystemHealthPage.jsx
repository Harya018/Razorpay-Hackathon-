import { useState } from "react";

import Card from "../../../components/Card.jsx";
import CheckpointSessionCard from "../../../components/CheckpointSessionCard.jsx";
import LLMResiliencePanel from "../../../components/LLMResiliencePanel.jsx";
import RecoverySimulationPanel from "../../../components/RecoverySimulationPanel.jsx";
import ServiceHealthGrid from "../../../components/ServiceHealthGrid.jsx";
import useDashboardStream from "../../../hooks/useDashboardStream.js";

export default function SystemHealthPage() {
  const [pingCount, setPingCount] = useState(0);
  const connected = useDashboardStream(() => {});

  return (
    <div className="space-y-4">
      <Card
        title="Service Health"
        action={
          <button onClick={() => setPingCount((c) => c + 1)} className="font-body text-xs text-clay hover:underline">
            Refresh
          </button>
        }
      >
        <ServiceHealthGrid key={pingCount} sseConnected={connected} />
      </Card>
      <LLMResiliencePanel />
      <CheckpointSessionCard />
      <RecoverySimulationPanel />
    </div>
  );
}
