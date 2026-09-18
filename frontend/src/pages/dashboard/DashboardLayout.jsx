import { NavLink, Outlet } from "react-router-dom";

function tabClass({ isActive }) {
  return `rounded-lg px-3 py-1.5 font-body text-sm font-medium transition-colors ${
    isActive ? "bg-clay text-ivory shadow-sm" : "text-ink-soft hover:bg-putty-light hover:text-ink"
  }`;
}

// New information architecture: MERCHANT = Overview | Analytics |
// Technical. Overview is the 10-second-understanding page; Analytics is
// the trends/business-metrics page (unchanged, just moved under
// /dashboard/analytics instead of the old top-level /analytics); Technical
// is its own nested layout (TechnicalLayout.jsx) with 7 further sub-tabs.
// "end" on the Overview link only — Technical's own NavLinks would
// otherwise never highlight while nested under /dashboard/technical/*.
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
          <NavLink to="/dashboard/orders" className={tabClass}>
            Orders
          </NavLink>
          <NavLink to="/dashboard/inventory" className={tabClass}>
            Inventory
          </NavLink>
          <NavLink to="/dashboard/analytics" className={tabClass}>
            Analytics
          </NavLink>
          <NavLink to="/dashboard/technical" className={tabClass}>
            Technical
          </NavLink>
        </div>
        <Outlet />
      </div>
    </div>
  );
}
