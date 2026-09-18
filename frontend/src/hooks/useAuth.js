import { useEffect, useState } from "react";

import { getAccessToken } from "../lib/auth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Calls the backend's GET /auth/me — the ONLY source of truth this
// frontend ever uses for "who am I / what's my role." This is UX-only:
// it decides what the frontend SHOWS (a login prompt vs. the dashboard
// vs. a "you're signed in but not an admin" message), never what the
// backend ALLOWS — every protected route independently re-verifies the
// token and re-derives the role itself (see backend/app/auth.py). A user
// cannot become MERCHANT_ADMIN by tampering with this hook's state; they'd
// still get a real 403 from the server the moment they tried to act on it.
export default function useAuth() {
  const [state, setState] = useState({ loading: true, user: null, error: null });

  useEffect(() => {
    let cancelled = false;
    const token = getAccessToken();
    if (!token) {
      setState({ loading: false, user: null, error: null });
      return undefined;
    }

    fetch(`${API_BASE_URL}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`auth check failed: ${res.status}`))))
      .then((user) => {
        if (!cancelled) setState({ loading: false, user, error: null });
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, user: null, error: err.message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { ...state, isAdmin: state.user?.role === "MERCHANT_ADMIN", isSignedIn: Boolean(state.user) };
}
