import { NavLink, Outlet } from "react-router-dom";

function tabClass({ isActive }) {
  return `rounded-lg px-3 py-1.5 font-body text-sm font-medium transition-colors ${
    isActive ? "bg-clay text-ivory shadow-sm" : "text-ink-soft hover:bg-putty-light hover:text-ink"
  }`;
}

// Wraps all three dashboard pages (Overview, Human Negotiations, AI Buyer
// Agents) with a shared sub-nav tab bar — this IS the "navigation into
// the two sub-pages" the Overview page needs, and it also lets a
// merchant already on one sub-page jump straight to the other, not just
// back to Overview first.
//
// Phase 19 shell rebuild: moved from the Phase 16 dark-slate "instrument
// panel" shell to the same light cream/warm-brown family as the
// storefront, per this pass's explicit direction — the whole app should
// read as one product now, not two registers. The deterministic-vs-LLM
// color coding and the Audit Trail panel's own terminal/mono styling are
// UNCHANGED — this file only restyles its own shell chrome (the tab bar
// and background), never the panels rendered inside it.
export default function DashboardLayout() {
  return (
    <div className="min-h-screen bg-ivory">
      <div className="border-b border-putty-dark px-6 py-3">
        <p className="font-body text-[11px] font-medium uppercase tracking-widest text-ink-soft/70">Merchant Operations</p>
      </div>
      <div className="p-6">
        <div className="mb-5 inline-flex gap-1 rounded-xl border border-putty-dark bg-white p-1 shadow-sm">
          <NavLink to="/dashboard" end className={tabClass}>
            Overview
          </NavLink>
          <NavLink to="/dashboard/negotiations" className={tabClass}>
            Human Negotiations
          </NavLink>
          <NavLink to="/dashboard/agent-conversations" className={tabClass}>
            AI Buyer Agents
          </NavLink>
        </div>
        <Outlet />
      </div>
    </div>
  );
}
