const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

const TOKEN_KEY = "bac_supabase_access_token";

export function installAuthFromUrl() {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const accessToken = hash.get("access_token");
  if (accessToken) {
    localStorage.setItem(TOKEN_KEY, accessToken);
    window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
  }
}

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

// redirectTo: where to land after Google sends the user back (default:
// the current page). The role is NOT chosen here — Supabase issues the
// token, the backend derives SHOPPER/MERCHANT_ADMIN from it; the login
// page only uses redirectTo to send a customer to /shop and a merchant
// to /dashboard, and the backend's 403 is what actually stops a shopper
// who lands on /dashboard anyway.
export function signInWithGoogle(redirectTo) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Supabase frontend config is missing");
  }
  const target = window.location.origin + (redirectTo || window.location.pathname);
  const params = new URLSearchParams({ provider: "google", redirect_to: target });
  window.location.href = `${SUPABASE_URL}/auth/v1/authorize?${params.toString()}`;
}

// One-click demo sign-in — calls the backend's POST /auth/demo-login,
// which only responds when DEMO_MODE=1 is set there (see
// backend/app/routes/auth.py). Used instead of signInWithGoogle() when no
// real Supabase project is configured (VITE_SUPABASE_URL/ANON_KEY unset),
// which is the normal state for a local/demo checkout of this project.
// The token that comes back is a REAL, signed Supabase-shaped JWT —
// verified by the backend's real require_user()/require_merchant_admin()
// path exactly like a genuine Google-issued one, not a client-side stub.
// role: "shopper" | "merchant" — which demo persona to mint.
export async function signInDemo(role = "merchant", redirectTo = null) {
  const res = await fetch(`${API_BASE_URL}/auth/demo-login?role=${encodeURIComponent(role)}`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Demo sign-in is not available");
  }
  const { access_token } = await res.json();
  localStorage.setItem(TOKEN_KEY, access_token);
  window.location.href = redirectTo || window.location.pathname;
}

export function isSupabaseConfigured() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

export function signOut() {
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = "/login";
}

// Attach the bearer token to EVERY call to our own backend (and only our
// backend — the URL must start with API_BASE_URL, so the token never
// leaves for a third party). Public routes simply ignore it; routes that
// attribute-when-present (checkout, so an order is tied to the signed-in
// customer) and routes that require it (orders, profile, dashboard,
// admin) all get it the same way.
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

export function withAuthQuery(url) {
  const token = getAccessToken();
  if (!token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}access_token=${encodeURIComponent(token)}`;
}