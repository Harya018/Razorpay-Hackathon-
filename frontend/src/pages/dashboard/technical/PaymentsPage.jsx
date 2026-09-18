import IdempotencyCard from "../../../components/IdempotencyCard.jsx";
import PaymentLogsPanel from "../../../components/PaymentLogsPanel.jsx";
import PaymentSecurityPanel from "../../../components/PaymentSecurityPanel.jsx";
import WebhookPanel from "../../../components/WebhookPanel.jsx";

export default function PaymentsPage() {
  return (
    <div className="space-y-4">
      <PaymentSecurityPanel />
      <PaymentLogsPanel />
      <WebhookPanel />
      <IdempotencyCard />
    </div>
  );
}
