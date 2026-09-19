import { useState } from "react";

import { signOut } from "../lib/auth.js";

// One sign-out control for every surface (customer sidebar, merchant
// sidebar, both profile pages). Disables itself while the real sign-out
// (server-side Supabase revoke + local session removal + navigation) is
// running so a double-click can't fire it twice.
export default function SignOutButton({ className = "", iconClass = "", labelClass = "", showIcon = false }) {
  const [busy, setBusy] = useState(false);

  async function handle() {
    if (busy) return;
    setBusy(true);
    await signOut(); // navigates to /login; never resolves back into a signed-in UI
  }

  return (
    <button type="button" onClick={handle} disabled={busy} title="Sign out" aria-busy={busy} className={`${className} disabled:opacity-60`}>
      {showIcon && <span className={iconClass}>{busy ? "⏳" : "🚪"}</span>}
      <span className={labelClass}>{busy ? "Signing out…" : "Sign out"}</span>
    </button>
  );
}
