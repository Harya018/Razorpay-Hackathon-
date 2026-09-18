import { NavLink, Outlet } from "react-router-dom";

const TABS = [
  { to: "/dashboard/technical", label: "Live Activity", end: true },
  { to: "/dashboard/technical/policy-gate", label: "Policy Gate" },
  { to: "/dashboard/technical/ai-agents", label: "AI Agents" },
  { to: "/dashboard/technical/security", label: "Security" },
  { to: "/dashboard/technical/audit-chain", label: "Audit Chain" },
  { to: "/dashboard/technical/payments", label: "Payments" },
  { to: "/dashboard/technical/system-health", label: "System Health" },
];

function tabClass({ isActive }) {
  return `whitespace-nowrap rounded-lg px-3 py-1.5 font-body text-xs font-medium transition-colors ${
    isActive ? "bg-ink text-ivory shadow-sm" : "text-ink-soft hover:bg-putty-light hover:text-ink"
  }`;
}

// The interview centerpiece — see TechnicalOverview's own architecture
// diagram (reused from SecurityTrustBoundaryPanel) for the "how AI
// negotiation is bounded before money moves" framing. Every sub-page here
// reuses an existing panel/component wherever one already exists; only
// genuinely new ground (Authorization Lifecycle, Token Security, Price
// Re-Verification, Webhooks, LLM Resilience, Checkpoint status) gets new
// components.
export default function TechnicalLayout() {
  return (
    <div>
      <div className="mb-1">
        <h1 className="font-display text-2xl font-semibold text-ink">Technical Control Center</h1>
        <p className="font-body text-sm text-ink-soft">Observe how AI negotiation is bounded before money moves.</p>
      </div>
      <div className="my-4 flex gap-1 overflow-x-auto rounded-xl border border-putty-dark bg-white p-1 shadow-sm">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className={tabClass}>
            {tab.label}
          </NavLink>
        ))}
      </div>
      <Outlet />
    </div>
  );
}
