import { useCallback, useEffect, useState } from "react";

import { getCart, markNegotiationTriggered } from "../lib/cart.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const THRESHOLD_SECONDS = Number(import.meta.env.VITE_CART_ABANDONMENT_THRESHOLD_SECONDS ?? 45);
const CHECK_INTERVAL_MS = 5000;

// Module-level (not component-level) in-flight guard — caught live: two
// overlapping checkNow() calls (React StrictMode's dev-only double-effect
// mount, or a slow /negotiate/start response still in flight when the
// next interval tick fires) could both read negotiationTriggered=false
// from localStorage before either had written it back, each starting its
// OWN real negotiation session for the same abandoned cart. A ref inside
// the hook wouldn't survive that remount; this does, since only one
// negotiation-worthy cart is ever active in this browser at a time.
let _negotiateStartInFlight = false;

// The real hesitation signal that replaces the old manual "Start
// negotiation" button (removed everywhere in Phase 10 — negotiation is
// now seller-initiated only). Runs an immediate check on mount (covers
// "closed the tab and reopened later than the threshold") plus a
// periodic interval (covers "left the tab open and idle past the
// threshold"). Calls the SAME real POST /negotiate/start the old manual
// button used to call — the seller agent, the staged discount ladder,
// and the policy gate are exactly the same real system either way; only
// what TRIGGERS the call has changed.
//
// checkNow (returned below) is the exact same function the interval
// calls — Phase 10's "leaving and returning to the app" demo overlay
// calls it too, on close, rather than duplicating this logic.
export default function useCartAbandonment() {
  const [notification, setNotification] = useState(null); // { sessionId, message, productId, proposedValue } | null

  // `force` is only ever true from the "simulate leaving and returning"
  // demo overlay (see forceCheck below) — it exists so that explicit demo
  // affordance reliably reproduces the popup every time it's used, rather
  // than being subject to the real elapsed-time gating an organic cart
  // abandonment goes through.
  const checkNow = useCallback(async (force = false) => {
    const cart = getCart();
    if (cart.items.length === 0) return;

    if (cart.negotiationTriggered) {
      // Already fired for SOME product (possibly on an earlier page load)
      // — just make sure the notification is showing; never call
      // /negotiate/start a second time while one is already pending.
      if (cart.negotiationSessionId) {
        setNotification({
          sessionId: cart.negotiationSessionId,
          message: cart.negotiationMessage,
          productId: cart.negotiationProductId,
          proposedValue: cart.negotiationProposedValue,
        });
      }
      return;
    }

    // Bug fixed Phase 20: this used to always negotiate about
    // cart.items[0] — the very FIRST product ever added — and, since
    // negotiationTriggered never cleared once set, every later item added
    // to the cart never got its own negotiation at all. Target the most
    // recently added item that hasn't already had one (dismissed or
    // accepted both count as "handled" — see resolveNegotiation in
    // cart.js), so each new product gets its own real shot.
    // `force` is a demo-only cheat: always re-target the newest item
    // regardless of history, so the "simulate leaving and returning"
    // button reliably reproduces a popup on demand even for a product
    // already negotiated this session.
    const handled = new Set(cart.negotiationHandledProductIds);
    const target = force
      ? [...cart.items].reverse()[0]
      : [...cart.items].reverse().find((i) => !handled.has(i.productId));
    // Bug fixed Phase 20: this used to setNotification(null) here, which
    // — now that resolveNegotiation clears negotiationTriggered the
    // instant a negotiation is ACCEPTED, not just dismissed — meant the
    // very next 5s background poll could unmount NegotiationNotification
    // entirely while the handoff view ("Pay now" / "Go to cart") was
    // still on screen, mid-interaction, with nothing new to negotiate
    // about yet. This hook only ever STARTS a notification now; hiding
    // an already-shown one is owned entirely by the component's own
    // local dismiss state (NegotiationNotification's manuallyClosed),
    // triggered by an explicit user action, never a background poll.
    if (!target) return;

    if (!force) {
      if (!cart.lastActivityAt) return;
      const elapsedSeconds = (Date.now() - cart.lastActivityAt) / 1000;
      if (elapsedSeconds < THRESHOLD_SECONDS) return;
    }

    if (_negotiateStartInFlight) return; // see module-level note above
    _negotiateStartInFlight = true;

    try {
      const res = await fetch(`${API_BASE_URL}/negotiate/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_id: target.productId, cart_quantity: target.quantity }),
      });
      if (!res.ok) return;
      const data = await res.json();
      const proposedValue = data.proposed_offer?.value ?? null;
      markNegotiationTriggered(data.session_id, data.message, target.productId, proposedValue);
      setNotification({ sessionId: data.session_id, message: data.message, productId: target.productId, proposedValue });
    } catch {
      // Best-effort — cart.negotiationTriggered stays false, so this is
      // retried on the next tick / next app load rather than lost.
    } finally {
      _negotiateStartInFlight = false;
    }
  }, []);

  useEffect(() => {
    checkNow();
    const interval = setInterval(checkNow, CHECK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [checkNow]);

  const forceCheck = useCallback(() => checkNow(true), [checkNow]);

  return { notification, checkNow, forceCheck };
}
