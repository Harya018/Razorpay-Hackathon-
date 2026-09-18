import { createClient } from "@supabase/supabase-js";

// Public, browser-safe config ONLY. The anon key is designed to ship in
// client bundles — it grants nothing by itself; every real authorization
// decision happens server-side (backend/app/auth.py) against the JWT this
// client's sign-in produces. A service-role key must never appear here.
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = () => Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

// Lazily created so an unconfigured local/demo build never instantiates
// a client against an empty URL.
let client = null;
export function getSupabase() {
  if (!isSupabaseConfigured()) return null;
  if (!client) {
    client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        flowType: "pkce", // authorization code + PKCE — no tokens in the URL fragment
        persistSession: true, // session (incl. refresh token) kept by the SDK in localStorage
        autoRefreshToken: true, // access token silently renewed before expiry
        detectSessionInUrl: true, // exchanges ?code=... on /auth/callback for a session
      },
    });
  }
  return client;
}
