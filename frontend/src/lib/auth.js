import { getSupabase, isSupabaseConfigured } from "./supabase.js";

export { isSupabaseConfigured };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";
const DEMO_TOKEN_KEY = "bac_demo_access_token";
const AUTH_CALLBACK_PATH = "/auth/callback";
// Where to send the user once sign-in completes. Kept in sessionStorage
// (this tab only, gone when the tab closes) rather than in the OAuth
// redirect's query string, because Supabase only honors a redirectTo that
// matches its Redirect URLs allow-list and silently falls back to the
// Site URL otherwise — a `?next=` on the callback URL is exactly the kind
// of thing that fails that match and loses the destination. With the
// destination held here, the callback URL is always the bare, fixed
// <origin>/auth/callback.
const DESTINATION_KEY = "bac_post_login_destination";

export function rememberDestination(path) {
  try {
    sessionStorage.setItem(DESTINATION_KEY, safeNext(path));
  } catch {
    // sessionStorage unavailable — the callback will fall back to /shop.
  }
}

// Read-once: the value is removed as soon as it's consumed so a stale
// destination can never leak into a later, unrelated sign-in.
export function consumeDestination(fallback = "/shop") {
  let value = null;
  try {
    value = sessionStorage.getItem(DESTINATION_KEY);
    sessionStorage.removeItem(DESTINATION_KEY);
  } catch {
    value = null;
  }
  return safeNext(value, fallback);
}

// Demo sign-in is an explicit, dev-only opt-in on BOTH sides: the frontend
// only offers it when VITE_DEMO_LOGIN=true AND no real Supabase project is
// configured, and the backend only honors it when DEMO_MODE=1. A
// production build with real Supabase config never shows it.
export const isDemoLoginEnabled = () => !isSupabaseConfigured() && import.meta.env.VITE_DEMO_LOGIN === "true";

// --- token access (synchronous, for the fetch interceptor + SSE URL) ------
// supabase-js owns the real session (and refreshes it); we mirror only the
// current access token into memory via onAuthStateChange so the rest of
// the app can read it synchronously. The demo persona uses its own key.
let supabaseAccessToken = "";

export function getAccessToken() {
  if (supabaseAccessToken) return supabaseAccessToken;
  try {
    return localStorage.getItem(DEMO_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

// Called once before the app renders (main.jsx). With Supabase configured
// this restores a persisted session AND — on /auth/callback — exchanges the
// PKCE ?code= for a session, so route guards never see a false "signed
// out" on first paint. Resolves regardless of outcome.
export async function initAuth() {
  const supabase = getSupabase();
  if (!supabase) return;
  supabase.auth.onAuthStateChange((_event, session) => {
    supabaseAccessToken = session?.access_token || "";
  });
  try {
    const { data } = await supabase.auth.getSession();
    supabaseAccessToken = data.session?.access_token || "";
  } catch {
    supabaseAccessToken = "";
  }
}

// --- open-redirect guard ----------------------------------------------------
// A post-login destination must be an APPROVED internal application path:
// a single leading "/" (never "//", "/\", or a scheme), no control chars,
// and its first segment must be one of the app's own route roots below.
// Anything else falls back to the role's default landing page. This is an
// allow-list, not a deny-list — an unknown path is rejected even if it is
// same-origin.
const APPROVED_NEXT_ROOTS = ["/shop", "/orders", "/profile", "/dashboard", "/catalog"];

export function safeNext(value, fallback = "/shop") {
  if (typeof value !== "string" || value.length === 0 || value.length > 512) return fallback;
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return fallback;
  if (/[\\\r\n\x00-\x1f]/.test(value) || /^\/[a-z][a-z0-9+.-]*:/i.test(value)) return fallback;
  const path = value.split(/[?#]/)[0];
  const approved = APPROVED_NEXT_ROOTS.some((root) => path === root || path.startsWith(`${root}/`));
  return approved ? value : fallback;
}

// --- sign-in ----------------------------------------------------------------
// Real Google sign-in through Supabase Auth (authorization code + PKCE).
// `next` is where the user wanted to go; it only decides the landing page
// after the callback — the ROLE is never chosen client-side. The backend
// re-derives SHOPPER/MERCHANT_ADMIN from the verified token on every
// request, and a non-merchant Google account landing on /dashboard simply
// gets its 403.
export async function signInWithGoogle(next) {
  const supabase = getSupabase();
  if (!supabase) throw new Error("Google sign-in isn't configured for this deployment");
  rememberDestination(next);
  // Fixed, query-free callback — the only entry the Supabase project's
  // Redirect URLs allow-list needs is exactly this URL.
  const redirectTo = `${window.location.origin}${AUTH_CALLBACK_PATH}`;
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo, queryParams: { prompt: "select_account" } },
  });
  if (error) throw new Error(error.message);
  // supabase-js navigates the browser to Google; nothing more to do here.
}

// Demo persona sign-in — see isDemoLoginEnabled. Calls the backend's
// DEMO_MODE-gated POST /auth/demo-login, which mints a real HS256 token the
// backend then verifies exactly like a Supabase-issued one. Deliberately
// finishes through the same /auth/callback page as the Google flow, so the
// destination handling is one code path, exercised by every sign-in.
export async function signInDemo(role = "shopper", next = null) {
  if (!isDemoLoginEnabled()) throw new Error("Demo sign-in is not enabled in this build");
  const res = await fetch(`${API_BASE_URL}/auth/demo-login?role=${encodeURIComponent(role)}`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Demo sign-in is not available");
  }
  const { access_token } = await res.json();
  rememberDestination(safeNext(next, role === "merchant" ? "/dashboard" : "/shop"));
  localStorage.setItem(DEMO_TOKEN_KEY, access_token);
  window.location.href = AUTH_CALLBACK_PATH;
}

// Real sign-out. Order matters: local state is cleared FIRST so that even
// if the network revoke fails, this browser cannot keep acting as the user.
// supabase.auth.signOut() revokes the refresh token server-side and drops
// the SDK's persisted session; if that call errors (offline, expired), the
// local-scope variant is used so the persisted session is still removed.
// Ends with a full navigation to /login, which discards every in-memory
// React state (useAuth's cached user/role included) — nothing from the
// previous session survives a refresh.
let signOutInFlight = null;
export function signOut() {
  if (signOutInFlight) return signOutInFlight;
  signOutInFlight = (async () => {
    supabaseAccessToken = "";
    try {
      localStorage.removeItem(DEMO_TOKEN_KEY);
      sessionStorage.removeItem(DESTINATION_KEY);
    } catch {
      // storage unavailable — nothing to clear
    }
    const supabase = getSupabase();
    if (supabase) {
      try {
        const { error } = await supabase.auth.signOut();
        if (error) await supabase.auth.signOut({ scope: "local" });
      } catch {
        try {
          await supabase.auth.signOut({ scope: "local" });
        } catch {
          // best effort — local storage below is still gone
        }
      }
    }
    window.location.href = "/login";
  })();
  return signOutInFlight;
}

// --- transport --------------------------------------------------------------
// Attach the bearer token to EVERY call to our own backend (and only our
// backend — the URL must start with API_BASE_URL, so the token never
// leaves for a third party). Public routes simply ignore it; routes that
// attribute-when-present (checkout) and routes that require it (orders,
// profile, dashboard, admin) all get it the same way.
export function installAuthFetch() {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = typeof input === "string" ? input : input?.url || "";
    const token = getAccessToken();
    if (token && API_BASE_URL && url.startsWith(API_BASE_URL)) {
      const headers = new Headers(init.headers || {});
      headers.set("Authorization", `Bearer ${token}`);
      return originalFetch(input, { ...init, headers });
    }
    return originalFetch(input, init);
  };
}

// EventSource can't send headers — the SSE endpoint accepts the token as a
// query param instead (backend require_user reads both).
export function withAuthQuery(url) {
  const token = getAccessToken();
  if (!token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}access_token=${encodeURIComponent(token)}`;
}
