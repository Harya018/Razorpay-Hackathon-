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
    // Bug fixed Phase 20: this cart used to negotiate about cart.items[0]
    // ONLY, ever — once negotiationTriggered was true, EVERY later
    // checkNow() just re-showed that same first product's session
    // forever, so adding a second product to the cart never got its own
    // offer at all. negotiationHandledProductIds tracks every product
    // that has already had a negotiation attempt (dismissed OR accepted)
    // for THIS cart's lifecycle, so useCartAbandonment can move on to the
    // next distinct item instead of getting stuck on the first one.
    negotiationHandledProductIds: [],
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
    cart.negotiationHandledProductIds = [];
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

// Marks a product's negotiation as RESOLVED — declined, accepted, or
// otherwise concluded — so it's never re-offered again (organically) for
// this cart, and clears the "currently pending" session fields so
// useCartAbandonment is free to consider the next distinct cart item.
// Shared by dismissNegotiation and markNegotiationAccepted below; not
// exported on its own since every caller means one of those two things.
function resolveNegotiation(cart, productId) {
  if (productId != null && !cart.negotiationHandledProductIds.includes(productId)) {
    cart.negotiationHandledProductIds = [...cart.negotiationHandledProductIds, productId];
  }
  cart.negotiationTriggered = false;
  cart.negotiationSessionId = null;
  cart.negotiationMessage = null;
  cart.negotiationProductId = null;
  cart.negotiationProposedValue = null;
  cart.negotiationOpened = false;
  return cart;
}

// "Dismiss" on the popup — per Phase 10's spec, this keeps the original
// price for this product and stops IT specifically from resurfacing. Bug
// fixed Phase 20: this used to just set a cart-wide negotiationDismissed
// flag that silenced the popup forever, for every product, for the rest
// of this cart's lifecycle. Now it resolves only the product that was
// actually declined — a different item added afterward still gets its
// own real shot at a negotiation.
export function dismissNegotiation() {
  const cart = getCart();
  resolveNegotiation(cart, cart.negotiationProductId);
  saveCart(cart);
  return cart;
}

// Called once NegotiationPanel's handoff actually happens — a REAL
// gate-approved approval_token for a REAL final amount, not a client-side
// guess. product_id is recorded so Cart.jsx only ever applies this to the
// one line it actually belongs to. Also resolves this product's pending
// negotiation (same as a dismiss, just accepted instead of declined) so a
// different cart item is free to get its own offer.
export function markNegotiationAccepted(productId, { approvalToken, checkoutAmount, sessionId }) {
  const cart = getCart();
  resolveNegotiation(cart, productId);
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
