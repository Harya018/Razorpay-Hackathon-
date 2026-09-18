import AgentConversationsPage from "../AgentConversationsPage.jsx";

// Thin re-export under the new IA — the component itself (conversation
// list + chat thread, buyer-agent-vs-gate bubble distinction) is
// unchanged and unduplicated; only its route location moved, from the
// old /dashboard/agent-conversations to /dashboard/technical/ai-agents.
export default function AIAgentsPage() {
  return <AgentConversationsPage />;
}
