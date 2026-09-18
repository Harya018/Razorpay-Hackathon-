import { Link, Navigate, useLocation } from "react-router-dom";

import useAuth from "../hooks/useAuth.js";

// Wraps a merchant-only page (Merchant Dashboard, Catalog admin). This is
// a UX convenience, not the real security boundary — it just avoids
// showing a broken, half-loaded page full of failed-fetch errors to
// someone who was never going to see real data anyway. The actual
// boundary is server-side (every request these pages make is
// independently re-checked by backend/app/auth.py's
// require_merchant_admin), so even if this component were bypassed
// entirely (dev tools, a stale build, whatever), no protected data or
// action becomes reachable — the backend would just return 401/403.
export default function RequireAdmin({ children }) {
  const { loading, isSignedIn, isAdmin, user } = useAuth();
  const location = useLocation();

  if (loading) {
    return <p className="p-6 font-body text-sm text-ink-soft">Checking access…</p>;
  }

  if (!isSignedIn) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}&as=merchant`} replace />;
  }

  if (!isAdmin) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-2xl border border-rose-300 bg-rose-50 p-6 text-center shadow-sm">
        <p className="font-display text-lg font-semibold text-ink">Not authorized</p>
        <p className="mt-2 font-body text-sm text-ink-soft">
          You're signed in as <span className="font-medium text-ink">{user?.email || "an unrecognized account"}</span> with
          role <span className="font-mono text-xs">{user?.role}</span>. This area is for the merchant account only — the
          backend rejected the request (403), and this page is just telling you so.
        </p>
        <div className="mt-4 flex justify-center gap-2">
          <Link to="/shop" className="rounded-lg bg-clay px-4 py-2 font-body text-sm font-semibold text-ivory hover:bg-clay-dark">
            Back to shop
          </Link>
          <Link to="/login?as=merchant" className="rounded-lg border border-putty-dark px-4 py-2 font-body text-sm font-medium text-ink-soft hover:bg-putty-light">
            Switch account
          </Link>
        </div>
      </div>
    );
  }

  return children;
}
