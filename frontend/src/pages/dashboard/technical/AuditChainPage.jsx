import AuditTrailPanel from "../../../components/AuditTrailPanel.jsx";
import AuthorizationLifecyclePanel from "../../../components/AuthorizationLifecyclePanel.jsx";

export default function AuditChainPage() {
  return (
    <div className="space-y-4">
      <AuthorizationLifecyclePanel />
      <AuditTrailPanel />
    </div>
  );
}
