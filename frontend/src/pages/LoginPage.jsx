import { useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import useAuth from "../hooks/useAuth.js";
import { isDemoLoginEnabled, isSupabaseConfigured, safeNext, signInDemo, signInWithGoogle } from "../lib/auth.js";
import { toastError } from "../lib/toast.js";

// One authentication system (Supabase Google sign-in, or — in an
// explicitly enabled dev/demo build only — the DEMO_MODE stand-in), two
// entry points. Picking "Customer" vs "Merchant" here only decides where
// to send the user afterwards — it never decides their ROLE. The backend
// re-derives the role from the verified token on every request, so a
// customer who picks "Merchant Portal" simply lands on /dashboard and is
// shown the backend's 403 (see RequireAdmin.jsx). `next` is allow-listed
// to a same-origin path (safeNext) before it is ever used.
function Option({ title, tagline, cta, onClick, busy, accent }) {
  return (
    <div className="flex flex-1 flex-col rounded-2xl border border-putty-dark bg-white p-6 shadow-sm">
      <p className="font-body text-[11px] font-semibold uppercase tracking-widest text-ink-soft">{title}</p>
      <p className="mt-2 flex-1 font-body text-sm text-ink-soft">{tagline}</p>
      <button
        onClick={onClick}
        disabled={busy}
        className={`mt-5 w-full rounded-lg px-4 py-2.5 font-body text-sm font-semibold shadow-sm transition-colors disabled:opacity-60 ${
          accent ? "bg-clay text-ivory hover:bg-clay-dark" : "border border-ink bg-ink text-ivory hover:bg-ink/90"
        }`}
      >
        {busy ? "Redirecting…" : cta}
      </button>
    </div>
  );
}

export default function LoginPage() {
  const { loading, isSignedIn, isAdmin } = useAuth();
  const [params] = useSearchParams();
  const [busy, setBusy] = useState(null);
  const supabaseReady = isSupabaseConfigured();
  const demoReady = isDemoLoginEnabled();
  const rawNext = params.get("next");

  if (!loading && isSignedIn) {
    return <Navigate to={safeNext(rawNext, isAdmin ? "/dashboard" : "/shop")} replace />;
  }

  async function go(role) {
    const target = safeNext(rawNext, role === "merchant" ? "/dashboard" : "/shop");
    setBusy(role);
    try {
      if (supabaseReady) await signInWithGoogle(target);
      else if (demoReady) await signInDemo(role, target);
      else throw new Error("No sign-in method is configured — set VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY.");
    } catch (err) {
      toastError(err.message);
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-12">
      <div className="mb-8 text-center">
        <h1 className="font-display text-3xl font-semibold text-ink">Bounded Agentic Checkout</h1>
        <p className="mt-2 font-body text-base text-ink-soft">
          AI agents can negotiate. <span className="font-medium text-ink">Deterministic policy decides.</span>
        </p>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row">
        <Option
          title="Customer"
          tagline="Shop products, negotiate offers with the seller AI, and check out securely with Razorpay Test Mode."
          cta={supabaseReady ? "Continue with Google" : "Continue as Customer"}
          onClick={() => go("shopper")}
          busy={busy === "shopper"}
          accent
        />
        <Option
          title="Merchant"
          tagline="Manage products and inventory, inspect orders, payments, Policy Gate decisions and the audit chain."
          cta={supabaseReady ? "Merchant Portal — sign in with Google" : "Merchant Portal"}
          onClick={() => go("merchant")}
          busy={busy === "merchant"}
        />
      </div>

      <p className="mt-6 text-center font-body text-[11px] text-ink-soft/60">
        {supabaseReady
          ? "One Google sign-in for both. Your role is decided server-side from the verified token — not by which button you pressed. Merchant access requires an account the backend has configured as a merchant."
          : demoReady
            ? "Demo build: no Google account needed. Each button signs you in as a real, server-signed demo identity; the backend still decides the role."
            : "Sign-in is not configured for this build."}
      </p>
    </div>
  );
}
