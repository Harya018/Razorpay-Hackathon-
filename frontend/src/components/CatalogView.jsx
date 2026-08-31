import { useEffect, useState } from "react";

import { startCheckout } from "../lib/checkout.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Phase 10: negotiation is seller-initiated only (the real cart-
// abandonment trigger, see useCartAbandonment.js) — there is no manual
// "Start negotiation" affordance anywhere in the app any more, including
// this admin catalog view.
export default function CatalogView() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);
  const [checkingOutId, setCheckingOutId] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/catalog`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load catalog");
        return res.json();
      })
      .then(setProducts)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleBuy(product) {
    // Phase 18.6 — same double-click-fires-two-orders bug found and
    // fixed on ProductDetail.jsx's Buy Now; this list has one button per
    // product, so the guard is keyed by product id rather than a single
    // flag.
    if (checkingOutId) return;
    setCheckingOutId(product.id);
    setError(null);
    setStatusMessage(null);
    try {
      await startCheckout({ product, onStatus: setStatusMessage, onClose: () => setCheckingOutId(null) });
    } catch (err) {
      setError(err.message);
      setCheckingOutId(null);
    }
  }

  if (loading) return <p className="font-body text-sm text-ink-soft">Loading catalog...</p>;
  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;

  // Deliberately plainer than the shop's own ProductCard grid — this is
  // an internal tool, not a customer-facing surface — but it shares the
  // shop's actual identity (ivory/putty/clay/ink, serif name + plain sans
  // body) rather than the old generic white-and-blue admin look.
  return (
    <div>
      {statusMessage && (
        <p className="mb-4 inline-block rounded-sm border border-moss-light bg-moss-light/20 px-3 py-2 font-body text-sm font-medium text-moss-dark">
          {statusMessage}
        </p>
      )}
      <ul className="space-y-3">
        {products.map((product) => {
          const inStock = product.stock > 0;
          return (
            <li key={product.id} className="rounded-md border border-putty-dark bg-ivory p-5">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-display text-lg font-medium text-ink">{product.name}</p>
                    {product.negotiable && (
                      <span className="shrink-0 rounded-full bg-moss-light/25 px-2 py-0.5 font-body text-xs font-medium uppercase tracking-wide text-moss-dark">
                        Negotiable
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex items-baseline gap-2">
                    <p className="font-body text-2xl font-bold text-ink">₹{(product.price / 100).toFixed(2)}</p>
                    <p className="font-body text-sm text-ink-soft/60">stock: {product.stock}</p>
                  </div>
                  {product.description && <p className="mt-1 font-body text-sm text-ink-soft">{product.description}</p>}
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => handleBuy(product)}
                    disabled={!inStock || checkingOutId === product.id}
                    className="rounded-sm bg-clay px-5 py-2 font-body text-sm font-semibold text-ivory shadow-sm transition-colors hover:bg-clay-dark disabled:bg-putty disabled:text-ink-soft/50"
                  >
                    {checkingOutId === product.id ? "Opening..." : "Buy"}
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
