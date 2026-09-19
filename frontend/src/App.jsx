import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";

import CatalogView from "./components/CatalogView.jsx";
import LeaveAppOverlay from "./components/LeaveAppOverlay.jsx";
import NegotiationNotification from "./components/NegotiationNotification.jsx";
import RequireAdmin from "./components/RequireAdmin.jsx";
import RequireAuth from "./components/RequireAuth.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ToastHost from "./components/ToastHost.jsx";
import useCartAbandonment from "./hooks/useCartAbandonment.js";
import { getCart, getCartItemCount } from "./lib/cart.js";
import Cart from "./pages/Cart.jsx";
import DashboardLayout from "./pages/dashboard/DashboardLayout.jsx";
import InventoryPage from "./pages/dashboard/InventoryPage.jsx";
import MerchantOrderDetailPage from "./pages/dashboard/MerchantOrderDetailPage.jsx";
import MerchantOrdersPage from "./pages/dashboard/MerchantOrdersPage.jsx";
import OverviewPage from "./pages/dashboard/OverviewPage.jsx";
import AuthCallbackPage from "./pages/AuthCallbackPage.jsx";
import InvoicePage from "./pages/InvoicePage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import OrderDetailPage from "./pages/OrderDetailPage.jsx";
import OrdersPage from "./pages/OrdersPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import AIAgentsPage from "./pages/dashboard/technical/AIAgentsPage.jsx";
import AuditChainPage from "./pages/dashboard/technical/AuditChainPage.jsx";
import LiveActivityPage from "./pages/dashboard/technical/LiveActivityPage.jsx";
import PaymentsPage from "./pages/dashboard/technical/PaymentsPage.jsx";
import PolicyGatePage from "./pages/dashboard/technical/PolicyGatePage.jsx";
import SecurityPage from "./pages/dashboard/technical/SecurityPage.jsx";
import SystemHealthPage from "./pages/dashboard/technical/SystemHealthPage.jsx";
import TechnicalLayout from "./pages/dashboard/technical/TechnicalLayout.jsx";
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
        <ToastHost />
        <Sidebar cartCount={cartCount} />
        <div className="min-w-0 flex-1 overflow-x-hidden">
          <Routes>
            {/* The site root lands on the public storefront — a first-time
                visitor (or an interviewer opening the URL cold) should see
                the shop, not a merchant sign-in wall. The internal catalog
                admin view lives at /catalog. */}
            <Route path="/" element={<Navigate to="/shop" replace />} />
            <Route path="/login" element={<LoginPage />} />
            {/* Supabase's post-Google redirect target (PKCE code exchange
                already completed by initAuth() before render). Must be on
                the Supabase project's Redirect URLs allowlist. */}
            <Route path="/auth/callback" element={<AuthCallbackPage />} />

            {/* Customer account pages — any signed-in user; ownership is
                enforced server-side (GET /orders/{id} returns 404 for an
                order that isn't yours). */}
            <Route path="/profile" element={<RequireAuth><ProfilePage /></RequireAuth>} />
            <Route path="/orders" element={<RequireAuth><OrdersPage /></RequireAuth>} />
            <Route path="/orders/:orderId" element={<RequireAuth><OrderDetailPage /></RequireAuth>} />
            <Route path="/orders/:orderId/invoice" element={<RequireAuth><InvoicePage /></RequireAuth>} />

            <Route
              path="/catalog"
              element={
                <RequireAdmin>
                  <div className="min-h-screen bg-ivory p-4 sm:p-6">
                    <h1 className="font-display text-2xl font-semibold text-ink">Catalog (admin)</h1>
                    <p className="mb-5 mt-1 font-body text-sm text-ink-soft">
                      Internal view of Priya's Shop catalog — full product details, stock on hand, and a direct
                      buy-at-list-price action.
                    </p>
                    <CatalogView />
                  </div>
                </RequireAdmin>
              }
            />
            {/* New information architecture: MERCHANT = Overview | Analytics
                | Technical, all nested under /dashboard now (Analytics used
                to be a separate top-level /analytics route — moved here so
                the whole merchant experience lives under one gated tree,
                per this pass's explicit IA). Technical itself nests its own
                7 sub-pages (Live Activity, Policy Gate, AI Agents, Security,
                Audit Chain, Payments, System Health). */}
            <Route
              path="/dashboard"
              element={
                <RequireAdmin>
                  <DashboardLayout />
                </RequireAdmin>
              }
            >
              <Route index element={<OverviewPage />} />
              <Route path="orders" element={<MerchantOrdersPage />} />
              <Route path="orders/:orderId" element={<MerchantOrderDetailPage />} />
              <Route path="inventory" element={<InventoryPage />} />
              <Route path="profile" element={<ProfilePage merchant />} />
              <Route path="analytics" element={<SalesAnalyticsPage />} />
              <Route path="technical" element={<TechnicalLayout />}>
                <Route index element={<LiveActivityPage />} />
                <Route path="policy-gate" element={<PolicyGatePage />} />
                <Route path="ai-agents" element={<AIAgentsPage />} />
                <Route path="security" element={<SecurityPage />} />
                <Route path="audit-chain" element={<AuditChainPage />} />
                <Route path="payments" element={<PaymentsPage />} />
                <Route path="system-health" element={<SystemHealthPage />} />
              </Route>
            </Route>

            {/* The storefront now requires a signed-in customer (any role):
                after sign-out, refreshing /shop lands on /login rather than
                a guest storefront, and every order is attributed to a
                verified identity. */}
            <Route
              path="/shop"
              element={
                <RequireAuth>
                  <ShopLayout />
                </RequireAuth>
              }
            >
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
