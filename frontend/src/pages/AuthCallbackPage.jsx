import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { consumeDestination, getAccessToken } from "../lib/auth.js";
import { getSupabase } from "../lib/supabase.js";

// The fixed landing page for every sign-in (Google via Supabase, or the
// dev-only demo persona). By the time this renders, main.jsx's initAuth()
// has already let supabase-js exchange the PKCE ?code= for a session
// (detectSessionInUrl). This page only confirms a session exists and then
// goes to the destination remembered in sessionStorage before sign-in
// started — read once, removed, and re-validated through safeNext(). The
// URL's own query string is deliberately NOT consulted for the
// destination (only for Supabase's error reporting), so nothing here
// depends on a `?next=` surviving the OAuth round trip.
export default function AuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [problem, setProblem] = useState(null);
  // The stored destination is read-once, so this effect must run its
  // consume+navigate exactly once per page load — React StrictMode's
  // dev-only double-invocation of effects would otherwise consume it on
  // the first pass and send the second pass to the /shop fallback.
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return undefined;
    handledRef.current = true;
    const errorDescription = params.get("error_description") || params.get("error");
    if (errorDescription) {
      consumeDestination(); // discard — the sign-in did not happen
      setProblem(errorDescription);
      return;
    }
    (async () => {
      let token = getAccessToken();
      if (!token) {
        const supabase = getSupabase();
        const { data } = supabase ? await supabase.auth.getSession() : { data: {} };
        token = data?.session?.access_token || "";
      }
      if (!token) {
        consumeDestination();
        setProblem("Sign-in did not complete — no session was established.");
        return;
      }
      navigate(consumeDestination("/shop"), { replace: true });
    })();
    return undefined;
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
