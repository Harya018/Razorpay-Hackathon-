import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App.jsx";
import "./index.css";
import { initAuth, installAuthFetch } from "./lib/auth.js";

installAuthFetch();

// Restore any persisted Supabase session (and complete a PKCE code
// exchange on /auth/callback) BEFORE the first render, so route guards
// evaluate against the real signed-in state rather than a transient
// "signed out" that would bounce a returning user to /login.
initAuth().finally(() => {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
