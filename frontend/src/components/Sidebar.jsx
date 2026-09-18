import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import useAuth from "../hooks/useAuth.js";
import { signOut } from "../lib/auth.js";

// Persistent left nav. Icon-only below `sm` (labels hidden, not removed —
// still real links, still reachable) rather than a hamburger/drawer; a
// manual toggle lets the user collapse/expand on any viewport, remembered
// via localStorage.
//
// Role-aware: the list is built from the backend's own /auth/me answer
// (useAuth), never from a client-side flag — hiding a merchant link from a
// shopper is a courtesy, the backend's 403 is the actual boundary.
// Shop and Cart are both under /shop, so isActive is explicit per item
// rather than NavLink's prefix matching, so each highlights alone.
const SHOP = { to: "/shop", label: "Shop", icon: "🛍️", isActive: (p) => p === "/shop" || (p.startsWith("/shop/") && p !== "/shop/cart") };
const CART = { to: "/shop/cart", label: "Cart", icon: "🛒", isActive: (p) => p === "/shop/cart" };
const ORDERS = { to: "/orders", label: "Your Orders", icon: "📦", isActive: (p) => p.startsWith("/orders") };
const PROFILE = { to: "/profile", label: "Profile", icon: "👤", isActive: (p) => p === "/profile" };
const DASHBOARD = { to: "/dashboard", label: "Merchant Dashboard", icon: "📊", isActive: (p) => p.startsWith("/dashboard") && p !== "/dashboard/profile" };
const CATALOG = { to: "/catalog", label: "Catalog (admin)", icon: "📋", isActive: (p) => p === "/catalog" };
const MERCHANT_PROFILE = { to: "/dashboard/profile", label: "Merchant Profile", icon: "🏪", isActive: (p) => p === "/dashboard/profile" };

const STORAGE_KEY = "sidebar-collapsed";

export default function Sidebar({ cartCount }) {
  const { pathname } = useLocation();
  const { loading: authLoading, isSignedIn, isAdmin, user } = useAuth();
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

  const items = isAdmin ? [SHOP, CART, DASHBOARD, CATALOG, MERCHANT_PROFILE] : isSignedIn ? [SHOP, CART, ORDERS, PROFILE] : [SHOP, CART];

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
      {items.map((item) => (
        <NavLink key={item.to} to={item.to} className={linkClass(item.isActive(pathname))} title={item.label}>
          <span className="shrink-0 text-lg leading-none">{item.icon}</span>
          <span className={labelClass}>
            {item.label}
            {item.to === "/shop/cart" && cartCount > 0 ? ` (${cartCount})` : ""}
          </span>
        </NavLink>
      ))}

      <div className="mt-auto border-t border-putty-dark pt-2">
        {authLoading ? null : isSignedIn ? (
          <div className={collapsed ? "flex justify-center" : "px-1"}>
            <p className={`truncate font-body text-xs text-ink-soft ${collapsed ? "hidden" : "hidden sm:block"}`} title={user?.email}>
              {isAdmin ? "Merchant" : "Customer"} — {user?.email}
            </p>
            <button
              type="button"
              onClick={signOut}
              title="Sign out"
              className="mt-1 flex w-full items-center gap-3 rounded-lg px-3 py-2 font-body text-sm font-medium text-ink-soft transition-colors hover:bg-putty-light hover:text-ink"
            >
              <span className="shrink-0 text-lg leading-none">🚪</span>
              <span className={labelClass}>Sign out</span>
            </button>
          </div>
        ) : (
          <NavLink to="/login" className={linkClass(pathname === "/login")} title="Sign in">
            <span className="shrink-0 text-lg leading-none">🔑</span>
            <span className={labelClass}>Sign in</span>
          </NavLink>
        )}
      </div>
    </nav>
  );
}
