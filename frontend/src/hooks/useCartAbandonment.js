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

  const checkNow = useCallback(async () => {
    const cart = getCart();
    if (cart.items.length === 0) return;

    if (cart.negotiationDismissed) {
      setNotification(null);
      return;
    }

    if (cart.negotiationTriggered) {
      // Already fired (possibly on an earlier page load) — just make sure
      // the notification is showing; never call /negotiate/start again
      // for this cart.
      if (cart.negotiationSessionId) {
        setNotification((prev) =>
          prev?.sessionId === cart.negotiationSessionId
            ? prev
            : {
                sessionId: cart.negotiationSessionId,
                message: cart.negotiationMessage,
                productId: cart.negotiationProductId,
                proposedValue: cart.negotiationProposedValue,
              }
        );
      }
      return;
    }

    if (!cart.lastActivityAt) return;
    const elapsedSeconds = (Date.now() - cart.lastActivityAt) / 1000;
    if (elapsedSeconds < THRESHOLD_SECONDS) return;

    if (_negotiateStartInFlight) return; // see module-level note above
    _negotiateStartInFlight = true;

    // Cart has sat untouched past the threshold and we haven't triggered
    // yet for it — negotiate about the first item added (a cart-level
    // negotiation, one session at a time, matches the seller's per-product
    // negotiation endpoint).
    const firstItem = cart.items[0];
    try {
      const res = await fetch(`${API_BASE_URL}/negotiate/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_id: firstItem.productId, cart_quantity: firstItem.quantity }),
      });
      if (!res.ok) return;
      const data = await res.json();
      const proposedValue = data.proposed_offer?.value ?? null;
      markNegotiationTriggered(data.session_id, data.message, firstItem.productId, proposedValue);
      setNotification({ sessionId: data.session_id, message: data.message, productId: firstItem.productId, proposedValue });
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

  return { notification, checkNow };
}
