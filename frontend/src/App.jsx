import { BrowserRouter, Outlet, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";

import CatalogView from "./components/CatalogView.jsx";
import LeaveAppOverlay from "./components/LeaveAppOverlay.jsx";
import NegotiationNotification from "./components/NegotiationNotification.jsx";
import Sidebar from "./components/Sidebar.jsx";
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

// Wraps every /shop/* page — this is where the real cart-abandonment
// hesitation signal lives. It runs on every storefront page load/mount
// (an immediate check, plus a periodic one) and, once a cart has
// genuinely sat idle past the threshold, auto-starts a real negotiation
// session and surfaces it as a persistent notification. Scoped to the
// shop area only — "/", "/dashboard" are unaffected.
//
// Phase 10 also adds a "simulate leaving the app" demo overlay here —
// closing it calls forceCheck() (still the same real /negotiate/start
// path the interval timer uses), but bypassing the elapsed-time
// threshold and any earlier "dismissed" state. Bug fixed Phase 20: this
// used to call the plain checkNow(), which — once a cart's popup had
// been dismissed, or before the real abandonment threshold had elapsed —
// silently did nothing, so the demo button didn't reliably reproduce the
// popup "every time." forceCheck exists specifically so this explicit
// demo affordance always shows it.
function ShopLayout() {
  const { notification, forceCheck } = useCartAbandonment();
  const [showLeaveOverlay, setShowLeaveOverlay] = useState(false);

  return (
    <div className="min-h-screen bg-ivory">
      <Outlet />

      <button
        onClick={() => setShowLeaveOverlay(true)}
        title="Demo: simulate leaving and returning to the app"
        className="fixed bottom-4 left-20 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-putty-dark bg-ivory text-lg shadow-md transition-transform hover:scale-105 sm:left-64"
      >
        🏠
      </button>
      {showLeaveOverlay && (
        <LeaveAppOverlay
          onClose={() => {
            setShowLeaveOverlay(false);
            forceCheck();
          }}
        />
      )}

      <NegotiationNotification notification={notification} />
    </div>
  );
}

export default function App() {
  const [cartCount, setCartCount] = useState(0);

  useEffect(() => {
    function refresh() {
      setCartCount(getCartItemCount(getCart()));
    }
    refresh();
    window.addEventListener("cart:updated", refresh);
    return () => window.removeEventListener("cart:updated", refresh);
  }, []);

  return (
    <BrowserRouter>
      {/* Phase 19 shell rebuild: a persistent left sidebar replaces the
          old top tab bar, consistent across every top-level destination.
          Flex row: sidebar (fixed width, icon-only below `sm`) + a
          scrollable content column that owns its own height. */}
      <div className="flex min-h-screen bg-ivory">
        <Sidebar cartCount={cartCount} />
        <div className="min-w-0 flex-1 overflow-x-hidden">
          <Routes>
            <Route
              path="/"
              element={
                <div className="min-h-screen bg-ivory p-4 sm:p-6">
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
                though it shares the dashboard's visual register. */}
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
      </div>
    </BrowserRouter>
  );
}
