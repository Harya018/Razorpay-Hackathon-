import { NavLink, Outlet } from "react-router-dom";

function tabClass({ isActive }) {
  return `rounded-sm px-3 py-1.5 font-mono text-xs font-medium uppercase tracking-wide transition-colors ${
    isActive ? "bg-content text-panel" : "text-slate-400 hover:text-slate-100"
  }`;
}

// Wraps all three dashboard pages (Overview, Human Negotiations, AI Buyer
// Agents) with a shared sub-nav tab bar — this IS the "navigation into
// the two sub-pages" the Overview page needs, and it also lets a
// merchant already on one sub-page jump straight to the other, not just
// back to Overview first.
//
// Register 2 shell (Phase 16 design pass): a dark slate instrument
// housing around light "screen" content panels — see
// src/styles/dashboard-tokens.css for the full rationale. Deliberately
// does NOT borrow the storefront's warmth; this is Priya's shop's
// infrastructure, not the shop itself.
export default function DashboardLayout() {
  return (
    <div className="min-h-[calc(100vh-57px)] bg-panel">
      <div className="border-b border-white/10 px-6 py-3">
        <p className="font-mono text-[11px] uppercase tracking-widest text-slate-500">Merchant Operations</p>
      </div>
      <div className="p-6">
        <div className="mb-5 inline-flex gap-1 rounded-sm border border-white/10 bg-panel-raised p-1">
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
