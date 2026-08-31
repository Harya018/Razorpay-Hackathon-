import { BrowserRouter, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";

import CatalogView from "./components/CatalogView.jsx";
import LeaveAppOverlay from "./components/LeaveAppOverlay.jsx";
import NegotiationNotification from "./components/NegotiationNotification.jsx";
import useCartAbandonment from "./hooks/useCartAbandonment.js";
import { getCart, getCartItemCount } from "./lib/cart.js";
import Cart from "./pages/Cart.jsx";
import AgentConversationsPage from "./pages/dashboard/AgentConversationsPage.jsx";
import DashboardHome from "./pages/dashboard/DashboardHome.jsx";
import DashboardLayout from "./pages/dashboard/DashboardLayout.jsx";
import NegotiationsPage from "./pages/dashboard/NegotiationsPage.jsx";
import ProductDetail from "./pages/ProductDetail.jsx";
import SalesAnalyticsPage from "./pages/SalesAnalyticsPage.jsx";
import Storefront from "./pages/Storefront.jsx";

function NavBar() {
  const [cartCount, setCartCount] = useState(0);

  useEffect(() => {
    function refresh() {
      setCartCount(getCartItemCount(getCart()));
    }
    refresh();
    window.addEventListener("cart:updated", refresh);
    return () => window.removeEventListener("cart:updated", refresh);
  }, []);

  const linkClass = ({ isActive }) =>
    `shrink-0 whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors sm:px-3 ${
      isActive ? "bg-blue-50 text-blue-700" : "text-slate-500 hover:text-slate-900"
    }`;

  // overflow-x-auto + shrink-0/whitespace-nowrap on every child: below the
  // point where the brand name + all four links no longer fit, the bar
  // scrolls horizontally instead of each link's text wrapping onto several
  // lines (which used to blow the bar up to ~140px tall at 390px width).
  return (
    <nav className="flex items-center gap-3 overflow-x-auto border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
      <span className="mr-2 hidden shrink-0 whitespace-nowrap text-sm font-semibold tracking-tight text-slate-900 sm:inline">
        Bounded Agentic Checkout
      </span>
      <NavLink to="/shop" className={linkClass}>
        Shop
      </NavLink>
      <NavLink to="/" end className={linkClass}>
        Catalog (admin)
      </NavLink>
      <NavLink to="/dashboard" className={linkClass}>
        Merchant Dashboard
      </NavLink>
      <NavLink to="/analytics" className={linkClass}>
        Sales Analytics
      </NavLink>
      <NavLink to="/shop/cart" className={linkClass}>
        Cart{cartCount > 0 ? ` (${cartCount})` : ""}
      </NavLink>
    </nav>
  );
}

// Wraps every /shop/* page — this is where the real cart-abandonment
// hesitation signal lives. It runs on every storefront page load/mount
// (an immediate check, plus a periodic one) and, once a cart has
// genuinely sat idle past the threshold, auto-starts a real negotiation
// session and surfaces it as a persistent notification. Scoped to the
// shop area only — "/", "/dashboard" are unaffected.
//
// Phase 10 also adds a "simulate leaving the app" demo overlay here —
// closing it re-runs checkNow(), the EXACT SAME function the interval
// timer calls, so "left and came back" is checked with no separate logic.
function ShopLayout() {
  const { notification, checkNow } = useCartAbandonment();
  const [showLeaveOverlay, setShowLeaveOverlay] = useState(false);

  return (
    <div className="min-h-[calc(100vh-57px)] bg-ivory">
      <Outlet />

      <button
        onClick={() => setShowLeaveOverlay(true)}
        title="Demo: simulate leaving and returning to the app"
        className="fixed bottom-4 left-4 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-putty-dark bg-ivory text-lg shadow-md transition-transform hover:scale-105"
      >
        🏠
      </button>
      {showLeaveOverlay && (
        <LeaveAppOverlay
          onClose={() => {
            setShowLeaveOverlay(false);
            checkNow();
          }}
        />
      )}

      <NegotiationNotification notification={notification} />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <NavBar />
        <Routes>
          <Route
            path="/"
            element={
              <div className="min-h-[calc(100vh-57px)] bg-ivory p-4 sm:p-6">
                <h1 className="font-display text-2xl font-semibold text-ink">Catalog (admin)</h1>
                <p className="mb-5 mt-1 font-body text-sm text-ink-soft">
                  Internal view of Priya's Shop catalog — browse products, negotiate, or buy at the listed price.
                </p>
                <CatalogView />
              </div>
            }
          />
          <Route path="/dashboard" element={<DashboardLayout />}>
            <Route index element={<DashboardHome />} />
            <Route path="negotiations" element={<NegotiationsPage />} />
            <Route path="agent-conversations" element={<AgentConversationsPage />} />
          </Route>

          {/* Deliberately a top-level route, NOT nested under /dashboard —
              this is a distinct page (trends, not live events), even
              though it shares the dashboard's slate/mono visual register. */}
          <Route path="/analytics" element={<SalesAnalyticsPage />} />

          <Route path="/shop" element={<ShopLayout />}>
            <Route
              index
              element={
                <div className="p-4 sm:p-6">
                  <h1 className="font-display text-2xl font-semibold text-ink">Priya's Shop</h1>
                  <p className="mb-5 mt-1 font-body text-sm text-ink-soft">Handmade home decor, made in small batches.</p>
                  <Storefront />
                </div>
              }
            />
            <Route path="product/:id" element={<div className="p-4 sm:p-6"><ProductDetail /></div>} />
            <Route path="cart" element={<div className="p-4 sm:p-6"><Cart /></div>} />
          </Route>
        </Routes>
      </div>
    </BrowserRouter>
  );
}
