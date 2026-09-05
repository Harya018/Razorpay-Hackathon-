// Customer-side cart state, persisted in localStorage so it survives a
// page close/reopen within the same browser. This is ordinary UI state
// for a shopping cart — NOT the "artifacts-storage" restriction, which
// only applies to Claude-authored artifacts elsewhere in this workspace.
//
// Every mutation here also dispatches a "cart:updated" window event so
// any component (navbar badge, NegotiationNotification, Cart page) can
// stay in sync without a real state-management library — they just
// listen for that event and re-read getCart().

const STORAGE_KEY = "checkout_cart_v1";

function emptyCart() {
  return {
    items: [], // [{ productId, quantity, addedAt }]
    lastActivityAt: null,
    negotiationTriggered: false,
    negotiationSessionId: null,
    negotiationMessage: null,
    negotiationOpened: false,
    negotiationProductId: null,
    negotiationProposedValue: null, // paise — the real gate-approved offer's total price
    negotiationDismissed: false, // Phase 10: user clicked "Dismiss" — stop resurfacing this session's popup
    // Phase 20 — set once a negotiation actually reaches a real gate-approved
    // handoff (NegotiationPanel's `handoff` state), so the discount survives
    // past the popup itself: Cart.jsx reads these to show the negotiated
    // price for the matching line and to redeem the SAME approval_token at
    // checkout, instead of the negotiated price only ever existing inside
    // the popup's own one-shot "Proceed to checkout" button.
    negotiationAccepted: false,
    negotiationAcceptedProductId: null,
    negotiationApprovalToken: null,
    negotiationCheckoutAmount: null, // paise — the real gate-approved total for this line
    negotiationAcceptedSessionId: null,
  };
}

export function getCart() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyCart();
    const parsed = JSON.parse(raw);
    return { ...emptyCart(), ...parsed };
  } catch {
    return emptyCart();
  }
}

function saveCart(cart) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
  } catch {
    // Best-effort — a full/blocked localStorage shouldn't crash the app.
  }
  window.dispatchEvent(new Event("cart:updated"));
}

export function addToCart(productId, quantity = 1) {
  const cart = getCart();
  const wasEmpty = cart.items.length === 0;

  const existing = cart.items.find((i) => i.productId === productId);
  if (existing) {
    existing.quantity += quantity;
  } else {
    cart.items.push({ productId, quantity, addedAt: Date.now() });
  }
  cart.lastActivityAt = Date.now();

  // A cart that just went from empty -> non-empty is a fresh lifecycle —
  // any previous negotiation state belonged to an earlier, since-cleared
  // cart and shouldn't carry over.
  if (wasEmpty) {
    cart.negotiationTriggered = false;
    cart.negotiationSessionId = null;
    cart.negotiationMessage = null;
    cart.negotiationOpened = false;
    cart.negotiationProposedValue = null;
    cart.negotiationDismissed = false;
    cart.negotiationAccepted = false;
    cart.negotiationAcceptedProductId = null;
    cart.negotiationApprovalToken = null;
    cart.negotiationCheckoutAmount = null;
    cart.negotiationAcceptedSessionId = null;
  }

  saveCart(cart);
  return cart;
}

export function updateQuantity(productId, quantity) {
  const cart = getCart();
  if (quantity <= 0) {
    cart.items = cart.items.filter((i) => i.productId !== productId);
  } else {
    const existing = cart.items.find((i) => i.productId === productId);
    if (existing) existing.quantity = quantity;
  }
  cart.lastActivityAt = Date.now();
  saveCart(cart);
  return cart;
}

export function removeFromCart(productId) {
  return updateQuantity(productId, 0);
}

// Called once an order is actually placed — starts the next cart's
// lifecycle clean, including the negotiation-abandonment flags.
export function clearCart() {
  saveCart(emptyCart());
}

export function getCartItemCount(cart = getCart()) {
  return cart.items.reduce((sum, i) => sum + i.quantity, 0);
}

// Marks that useCartAbandonment already auto-started a negotiation for
// THIS cart — the one-time-per-abandoned-cart guard the hook checks
// before ever calling POST /negotiate/start.
export function markNegotiationTriggered(sessionId, message, productId, proposedValue = null) {
  const cart = getCart();
  cart.negotiationTriggered = true;
  cart.negotiationSessionId = sessionId;
  cart.negotiationMessage = message;
  cart.negotiationProductId = productId;
  cart.negotiationProposedValue = proposedValue;
  saveCart(cart);
  return cart;
}

export function markNegotiationOpened() {
  const cart = getCart();
  cart.negotiationOpened = true;
  saveCart(cart);
  return cart;
}

// "Dismiss" on the popup — per Phase 10's spec, this keeps the original
// price and stops the popup from resurfacing for this cart/session. It
// does NOT clear negotiationSessionId/Message — the real negotiation
// session on the backend is untouched, just no longer surfaced in the UI.
export function dismissNegotiation() {
  const cart = getCart();
  cart.negotiationDismissed = true;
  saveCart(cart);
  return cart;
}

// Called once NegotiationPanel's handoff actually happens — a REAL
// gate-approved approval_token for a REAL final amount, not a client-side
// guess. product_id is recorded so Cart.jsx only ever applies this to the
// one line it actually belongs to.
export function markNegotiationAccepted(productId, { approvalToken, checkoutAmount, sessionId }) {
  const cart = getCart();
  cart.negotiationAccepted = true;
  cart.negotiationAcceptedProductId = productId;
  cart.negotiationApprovalToken = approvalToken;
  cart.negotiationCheckoutAmount = checkoutAmount;
  cart.negotiationAcceptedSessionId = sessionId;
  saveCart(cart);
  return cart;
}

// Called once the accepted negotiation's approval_token has actually been
// redeemed (a real order placed with it) — the token is single-use on the
// backend regardless, but clearing this locally stops Cart.jsx from
// continuing to show a price that's no longer honorable.
export function clearNegotiationAccepted() {
  const cart = getCart();
  cart.negotiationAccepted = false;
  cart.negotiationAcceptedProductId = null;
  cart.negotiationApprovalToken = null;
  cart.negotiationCheckoutAmount = null;
  cart.negotiationAcceptedSessionId = null;
  saveCart(cart);
  return cart;
}

// Used only by the "simulate leaving and returning" demo overlay's forced
// re-check (useCartAbandonment's forceCheck) — lets that demo affordance
// resurface an already-dismissed popup on demand, without touching the
// real once-dismissed-stays-dismissed behavior for an organic abandonment.
export function undismissNegotiation() {
  const cart = getCart();
  cart.negotiationDismissed = false;
  saveCart(cart);
  return cart;
}
