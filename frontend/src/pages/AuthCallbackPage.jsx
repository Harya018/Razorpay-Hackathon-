import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { getAccessToken, safeNext } from "../lib/auth.js";
import { getSupabase } from "../lib/supabase.js";

// Landing page for Supabase's redirect after Google. By the time this
// renders, main.jsx's initAuth() has already let supabase-js exchange the
// PKCE ?code= for a session (detectSessionInUrl) — so this page only has
// to confirm a session exists, sanitize `next`, and go there. Supabase
// reports a failed/denied login via ?error= / ?error_description=, which
// is shown instead of silently bouncing to /login.
export default function AuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [problem, setProblem] = useState(null);

  useEffect(() => {
    const errorDescription = params.get("error_description") || params.get("error");
    if (errorDescription) {
      setProblem(errorDescription);
      return;
    }
    let cancelled = false;
    (async () => {
      let token = getAccessToken();
      if (!token) {
        // Belt and braces: if the exchange hadn't finished by first render,
        // ask the SDK directly once more.
        const supabase = getSupabase();
        const { data } = supabase ? await supabase.auth.getSession() : { data: {} };
        token = data?.session?.access_token || "";
      }
      if (cancelled) return;
      if (!token) {
        setProblem("Sign-in did not complete — no session was established.");
        return;
      }
      navigate(safeNext(params.get("next")), { replace: true });
    })();
    return () => {
      cancelled = true;
    };
  }, [params, navigate]);

  if (problem) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-2xl border border-rose-300 bg-rose-50 p-6 text-center shadow-sm">
        <p className="font-display text-lg font-semibold text-ink">Sign-in failed</p>
        <p className="mt-2 font-body text-sm text-ink-soft">{problem}</p>
        <Link to="/login" className="mt-4 inline-block rounded-lg bg-clay px-4 py-2 font-body text-sm font-semibold text-ivory hover:bg-clay-dark">
          Back to sign-in
        </Link>
      </div>
    );
  }
  return <p className="p-6 font-body text-sm text-ink-soft">Completing sign-in…</p>;
}
