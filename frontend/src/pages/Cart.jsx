import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import RecommendationsRow from "../components/RecommendationsRow.jsx";
import { clearCart, getCart, removeFromCart, updateQuantity } from "../lib/cart.js";
import { startCheckout } from "../lib/checkout.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function Cart() {
  const [cart, setCart] = useState(getCart());
  const [products, setProducts] = useState({}); // productId -> product
  const [loading, setLoading] = useState(true);
  const [statusMessage, setStatusMessage] = useState(null);
  const [checkingOut, setCheckingOut] = useState(false);

  useEffect(() => {
    function refresh() {
      setCart(getCart());
    }
    window.addEventListener("cart:updated", refresh);
    return () => window.removeEventListener("cart:updated", refresh);
  }, []);

  useEffect(() => {
    fetch(`${API_BASE_URL}/catalog`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setProducts(Object.fromEntries(data.map((p) => [p.id, p]))))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="font-body text-sm text-ink-soft">Loading cart...</p>;

  const lines = cart.items
    .map((item) => ({ item, product: products[item.productId] }))
    .filter((line) => line.product);

  const subtotal = lines.reduce((sum, { item, product }) => sum + product.price * item.quantity, 0);

  if (lines.length === 0) {
    return (
      <div className="rounded-md border border-putty-dark bg-ivory p-8 text-center">
        <p className="font-body text-sm text-ink-soft">Your cart is empty.</p>
        <Link to="/shop" className="mt-3 inline-block font-body text-sm font-medium text-clay hover:text-clay-dark">
          Continue shopping →
        </Link>
      </div>
    );
  }

  // Checkout sequences through cart lines ONE Razorpay order/payment
  // modal at a time — this backend creates one order per product, so a
  // literal single "pay for everything at once" order doesn't exist.
  // Each line is removed from the cart as its payment is initiated;
  // once the last one closes, the cart (and any pending negotiation
  // state) is cleared.
  async function handleCheckoutAll() {
    setCheckingOut(true);
    setStatusMessage(null);
    const remaining = [...lines];

    async function next() {
      const line = remaining.shift();
      if (!line) {
        clearCart();
        setCheckingOut(false);
        setStatusMessage("All items checked out.");
        return;
      }
      try {
        await startCheckout({
          product: line.product,
          quantity: line.item.quantity,
          onStatus: setStatusMessage,
          onClose: () => {
            removeFromCart(line.item.productId);
            next();
          },
        });
      } catch (err) {
        setStatusMessage(err.message);
        setCheckingOut(false);
      }
    }
    next();
  }

  return (
    <div>
      <h1 className="mb-1 font-display text-2xl font-semibold text-ink">Your Cart</h1>
      <p className="mb-5 font-body text-sm text-ink-soft">
        Checkout processes one item at a time — each product is its own order.
      </p>

      {statusMessage && (
        <p className="mb-4 rounded-md bg-moss-light/20 px-3 py-2 font-body text-sm font-medium text-moss-dark">{statusMessage}</p>
      )}

      <ul className="space-y-3">
        {lines.map(({ item, product }) => (
          <li
            key={item.productId}
            className="flex items-center gap-4 rounded-md border border-putty-dark bg-ivory p-4"
          >
            <img
              src={product.image_urls?.[0]}
              alt={product.name}
              className="h-16 w-16 shrink-0 rounded-md object-cover"
            />
            <div className="min-w-0 flex-1">
              <Link to={`/shop/product/${product.id}`} className="font-body text-sm font-medium text-ink hover:text-clay">
                {product.name}
              </Link>
              <p className="mt-0.5 font-body text-sm text-ink-soft">₹{(product.price / 100).toFixed(2)} each</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => updateQuantity(item.productId, item.quantity - 1)}
                className="h-7 w-7 rounded-md border border-putty-dark text-ink-soft hover:bg-putty-light"
              >
                −
              </button>
              <span className="w-6 text-center font-body text-sm font-medium text-ink">{item.quantity}</span>
              <button
                onClick={() => updateQuantity(item.productId, item.quantity + 1)}
                className="h-7 w-7 rounded-md border border-putty-dark text-ink-soft hover:bg-putty-light"
              >
                +
              </button>
            </div>
            <p className="w-24 shrink-0 text-right font-body text-sm font-semibold text-ink">
              ₹{((product.price * item.quantity) / 100).toFixed(2)}
            </p>
            <button
              onClick={() => removeFromCart(item.productId)}
              className="shrink-0 font-body text-sm text-ink-soft/60 hover:text-rose-700"
            >
              Remove
            </button>
          </li>
        ))}
      </ul>

      <div className="mt-6 flex items-center justify-between rounded-md border border-putty-dark bg-ivory p-4">
        <div>
          <p className="font-body text-xs uppercase tracking-wide text-ink-soft/60">Subtotal</p>
          <p className="font-body text-xl font-bold text-ink">₹{(subtotal / 100).toFixed(2)}</p>
        </div>
        <button
          onClick={handleCheckoutAll}
          disabled={checkingOut}
          className="rounded-sm bg-clay px-6 py-2.5 font-body text-sm font-semibold text-ivory shadow-sm transition-colors hover:bg-clay-dark disabled:bg-putty"
        >
          {checkingOut ? "Checking out..." : "Checkout"}
        </button>
      </div>

      {/* Fills the dead space below a short (often single-item) cart list
          with something useful, rather than leaving a page's worth of
          empty ivory background under the summary box. */}
      <div className="mt-10">
        <RecommendationsRow
          allProducts={Object.values(products).filter((p) => !lines.some((line) => line.product.id === p.id))}
          currentProduct={lines[0].product}
        />
      </div>
    </div>
  );
}
