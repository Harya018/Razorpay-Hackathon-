import { useEffect, useState } from "react";

import CardShell from "./Card.jsx";
import StockBadge from "./StockBadge.jsx";
import { startCheckout } from "../lib/checkout.js";
import { toastError } from "../lib/toast.js";

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
      toastError(err.message);
      setCheckingOutId(null);
    }
  }

  if (loading) return <p className="font-body text-sm text-ink-soft">Loading catalog...</p>;
  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;

  // Phase 19: rows became cards (grid, not a stacked list) — same data,
  // same Buy handler/disabled logic, same stock/price display, just
  // laid out in the shared light-card family instead of a plain list.
  // Deliberately plainer than the shop's own ProductCard grid — this is
  // an internal tool, not a customer-facing surface — but it shares the
  // shop's actual identity (ivory/putty/clay/ink, serif name + plain sans
  // body) rather than the old generic white-and-blue admin look.
  //
  // Extended with a fuller per-product overview (ID, category, both
  // description fields, exact stock/status, rating, negotiability,
  // listed-since date) — every field here comes straight from the real
  // /catalog response (backend/app/schemas/product.py's ProductResponse),
  // nothing fabricated.
  return (
    <div>
      {statusMessage && (
        <p className="mb-4 inline-block rounded-full border border-moss-light bg-moss-light/20 px-3 py-2 font-body text-sm font-medium text-moss-dark">
          {statusMessage}
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {products.map((product) => {
          const inStock = product.stock > 0;
          return (
            <CardShell key={product.id} className="flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-display text-lg font-medium leading-tight text-ink">{product.name}</p>
                  <p className="mt-0.5 font-body text-[11px] text-ink-soft/50">
                    Product ID <span className="font-mono font-medium text-ink-soft">#{product.id}</span>
                    {product.category && <span className="ml-2 capitalize">— {product.category}</span>}
                  </p>
                </div>
                {product.negotiable && (
                  <span className="shrink-0 rounded-full bg-moss-light/25 px-2 py-0.5 font-body text-[10px] font-medium uppercase tracking-wide text-moss-dark">
                    Negotiable
                  </span>
                )}
              </div>

              <div className="mt-2 flex items-baseline gap-2">
                <p className="font-body text-2xl font-bold text-ink">₹{(product.price / 100).toFixed(2)}</p>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                <StockBadge stock={product.stock} size="md" />
                <span className="font-body text-xs text-ink-soft/50">{product.stock} units on hand</span>
              </div>

              {(product.description || product.detail_description) && (
                <div className="mt-2 space-y-1">
                  {product.description && <p className="font-body text-sm text-ink-soft">{product.description}</p>}
                  {product.detail_description && (
                    <p className="font-body text-xs text-ink-soft/70">{product.detail_description}</p>
                  )}
                </div>
              )}

              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-putty pt-2 font-body text-[11px] text-ink-soft/70">
                <p>
                  Rating:{" "}
                  <span className="font-medium text-ink-soft">
                    {product.rating != null ? `${product.rating.toFixed(1)} (${product.review_count ?? 0} reviews)` : "—"}
                  </span>
                </p>
                <p>
                  Listed since:{" "}
                  <span className="font-medium text-ink-soft">
                    {product.created_at ? new Date(product.created_at).toLocaleDateString() : "—"}
                  </span>
                </p>
              </div>

              <button
                onClick={() => handleBuy(product)}
                disabled={!inStock || checkingOutId === product.id}
                className="mt-3 rounded-lg bg-clay px-5 py-2 font-body text-sm font-semibold text-ivory shadow-sm transition-colors hover:bg-clay-dark disabled:bg-putty disabled:text-ink-soft/50"
              >
                {checkingOutId === product.id ? "Opening..." : "Buy"}
              </button>
            </CardShell>
          );
        })}
      </div>
    </div>
  );
}
