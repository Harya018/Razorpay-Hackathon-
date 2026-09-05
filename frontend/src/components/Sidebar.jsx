import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

// Persistent left nav, replacing the old top tab bar — same five
// destinations, same routes, just a different shell. Icon-only below
// `sm` (labels hidden, not removed — still real links, still reachable)
// rather than a hamburger/drawer: fewer moving parts, never fully hides
// navigation, and satisfies "collapse to icons-only or a hamburger, not
// break" without adding open/close state that has to be wired through
// every page. On top of that responsive collapse, a manual toggle lets
// the user collapse/expand the sidebar on any viewport; the choice is
// remembered across reloads via localStorage.
//
// Shop and Cart are both nested under /shop (Cart is /shop/cart), so a
// plain prefix-match NavLink would light up "Shop" AND "Cart" at once on
// the cart page. isActive is computed explicitly per item instead of via
// NavLink's own end/prefix matching so each destination highlights alone.
const NAV_ITEMS = [
  { to: "/shop", label: "Shop", icon: "🛍️", isActive: (p) => p === "/shop" || (p.startsWith("/shop/") && p !== "/shop/cart") },
  { to: "/", label: "Catalog (admin)", icon: "📋", isActive: (p) => p === "/" },
  { to: "/dashboard", label: "Merchant Dashboard", icon: "📊", isActive: (p) => p.startsWith("/dashboard") },
  { to: "/analytics", label: "Sales Analytics", icon: "📈", isActive: (p) => p === "/analytics" },
  { to: "/shop/cart", label: "Cart", icon: "🛒", isActive: (p) => p === "/shop/cart" },
];

const STORAGE_KEY = "sidebar-collapsed";

export default function Sidebar({ cartCount }) {
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // localStorage unavailable (private mode, etc.) — collapse state just won't persist.
    }
  }, [collapsed]);

  const linkClass = (active) =>
    `flex items-center gap-3 rounded-lg px-3 py-2.5 font-body text-sm font-medium transition-colors ${
      active ? "bg-clay text-ivory shadow-sm" : "text-ink-soft hover:bg-putty-light hover:text-ink"
    }`;
  const labelClass = collapsed ? "hidden" : "hidden truncate sm:inline";

  return (
    <nav
      className={`flex h-screen shrink-0 flex-col gap-1 border-r border-putty-dark bg-ivory-deep px-2 py-4 transition-[width] duration-150 ${
        collapsed ? "w-16" : "w-16 sm:w-60 sm:px-3"
      }`}
    >
      <div className={`mb-4 flex items-center px-1 ${collapsed ? "justify-center" : "justify-between sm:px-2"}`}>
        <div className={collapsed ? "hidden" : "hidden sm:block"}>
          <p className="font-display text-base font-semibold text-ink">Bounded Agentic</p>
          <p className="font-body text-xs text-ink-soft">Checkout</p>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Open menu" : "Close menu"}
          aria-label={collapsed ? "Open menu" : "Close menu"}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-soft hover:bg-putty-light hover:text-ink"
        >
          {collapsed ? "»" : "«"}
        </button>
      </div>
      {NAV_ITEMS.map((item) => (
        <NavLink key={item.to} to={item.to} className={linkClass(item.isActive(pathname))} title={item.label}>
          <span className="shrink-0 text-lg leading-none">{item.icon}</span>
          <span className={labelClass}>
            {item.label}
            {item.to === "/shop/cart" && cartCount > 0 ? ` (${cartCount})` : ""}
          </span>
        </NavLink>
      ))}
    </nav>
  );
}
