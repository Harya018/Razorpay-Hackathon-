import { Navigate, useLocation } from "react-router-dom";

import useAuth from "../hooks/useAuth.js";

// Any signed-in user (SHOPPER or MERCHANT_ADMIN). UX gate only — the
// routes behind it (/orders, /profile) are independently enforced
// server-side via require_user + ownership checks.
export default function RequireAuth({ children }) {
  const { loading, isSignedIn } = useAuth();
  const location = useLocation();

  if (loading) return <p className="p-6 font-body text-sm text-ink-soft">Checking access…</p>;
  if (!isSignedIn) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  return children;
}
