import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { StarRating } from "../components/ProductCard.jsx";
import RecommendationsRow from "../components/RecommendationsRow.jsx";
import ReviewsList from "../components/ReviewsList.jsx";
import StockBadge from "../components/StockBadge.jsx";
import { addToCart } from "../lib/cart.js";
import { startCheckout } from "../lib/checkout.js";
import { toastError, toastSuccess } from "../lib/toast.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Purely cosmetic monthly-installment display — no real EMI/financing
// provider is involved anywhere in this codebase. Simple price/n split.
const EMI_MONTH_OPTIONS = [3, 6, 12];

// Section 3's "Pricing & Policy" card — communicates the architecture
// (negotiation is available, but the FINAL price is set by the Policy
// Gate, not this page or the LLM) rather than exposing any internal
// discount-policy secrets.
function PricingPolicyCard({ price, negotiable }) {
  return (
    <div className="rounded-md border border-putty-dark bg-ivory-deep/40 p-3">
      <p className="font-body text-xs font-semibold uppercase tracking-wide text-ink-soft">Pricing &amp; Policy</p>
      <div className="mt-1.5 space-y-1 font-body text-sm">
        <div className="flex justify-between">
          <span className="text-ink-soft">Catalog price</span>
          <span className="font-medium text-ink">₹{(price / 100).toFixed(2)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-ink-soft">Negotiation</span>
          <span className={`font-medium ${negotiable ? "text-moss-dark" : "text-ink-soft/60"}`}>
            {negotiable ? "Available" : "Not available"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-ink-soft">Final price</span>
          <span className="font-medium text-ink">Determined by Policy Gate</span>
        </div>
      </div>
    </div>
  );
}

function EmiOptions({ price }) {
  return (
    <div className="rounded-md border border-putty-dark bg-ivory-deep/40 p-3">
      <p className="font-body text-xs font-semibold uppercase tracking-wide text-ink-soft">EMI options (illustrative)</p>
      <ul className="mt-1.5 space-y-1">
        {EMI_MONTH_OPTIONS.map((months) => (
          <li key={months} className="flex justify-between font-body text-sm text-ink-soft">
            <span>{months} months</span>
            <span className="font-medium text-ink">₹{(price / months / 100).toFixed(2)}/mo</span>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 font-body text-[11px] text-ink-soft/60">
        For illustration only — no financing provider is connected to this checkout.
      </p>
    </div>
  );
}

export default function ProductDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [product, setProduct] = useState(null);
  const [allProducts, setAllProducts] = useState([]);
  const [activeImage, setActiveImage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);
  const [checkingOut, setCheckingOut] = useState(false);
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    setLoading(true);
    setActiveImage(0);
    Promise.all([
      fetch(`${API_BASE_URL}/product/${id}`).then((res) => {
        if (!res.ok) throw new Error("Product not found");
        return res.json();
      }),
      fetch(`${API_BASE_URL}/catalog`).then((res) => (res.ok ? res.json() : [])),
    ])
      .then(([productData, catalogData]) => {
        setProduct(productData);
        setAllProducts(catalogData);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="font-body text-sm text-ink-soft">Loading product...</p>;
  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;
  if (!product) return null;

  const inStock = product.stock > 0 && product.is_active !== false;
  const images = product.image_urls?.length ? product.image_urls : [];
  // Clamp to what the backend says is on hand — purely a UX courtesy; the
  // backend re-checks stock at order creation and deducts atomically at
  // payment, so a manipulated quantity here cannot oversell.
  const qty = Math.min(Math.max(1, quantity), Math.max(1, product.stock));

  function handleAddToCart() {
    addToCart(product.id, qty);
    setStatusMessage(`Added ${qty} to cart.`);
    toastSuccess(`Added ${qty} × ${product.name} to cart.`);
  }

  async function handleBuyNow() {
    // Phase 18.6 — found live: a fast double-click fired two overlapping
    // POST /order/create calls (26ms apart), creating two separate real
    // Razorpay orders for one click's worth of intent. This guard makes
    // a second click while one checkout is already in flight a no-op,
    // same pattern Cart.jsx's handleCheckoutAll already used.
    if (checkingOut) return;
    setCheckingOut(true);
    setError(null);
    setStatusMessage(null);
    try {
      await startCheckout({ product, quantity: qty, onStatus: setStatusMessage, onClose: () => setCheckingOut(false) });
    } catch (err) {
      setError(err.message);
      toastError(err.message);
      setCheckingOut(false);
    }
  }

  return (
    <div>
      <button onClick={() => navigate(-1)} className="mb-4 font-body text-sm text-ink-soft hover:text-ink">
        ← Back
      </button>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <div>
          <div className="aspect-square w-full overflow-hidden rounded-[4px_18px_4px_18px] border border-putty-dark bg-putty-light">
            {images[activeImage] && (
              <img src={images[activeImage]} alt={product.name} className="h-full w-full object-cover" />
            )}
          </div>
          {images.length > 1 && (
            <div className="mt-2 flex gap-2">
              {images.map((url, i) => (
                <button
                  key={i}
                  onClick={() => setActiveImage(i)}
                  className={`h-16 w-16 shrink-0 overflow-hidden rounded-md border-2 ${
                    i === activeImage ? "border-clay" : "border-transparent"
                  }`}
                >
                  <img src={url} alt="" className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <div className="flex items-start justify-between gap-2">
              <h1 className="font-display text-2xl font-semibold text-ink">{product.name}</h1>
              {product.negotiable && (
                <span className="shrink-0 rounded-full bg-moss-light/25 px-2.5 py-1 text-xs font-medium text-moss-dark">
                  Negotiable
                </span>
              )}
            </div>
            <div className="mt-1">
              <StarRating rating={product.rating} reviewCount={product.review_count} />
            </div>
          </div>

          <p className="font-body text-3xl font-bold text-ink">₹{(product.price / 100).toFixed(2)}</p>
          <p className="font-body text-sm text-ink-soft">{product.description}</p>
          {product.detail_description && <p className="font-body text-sm text-ink-soft">{product.detail_description}</p>}
          <div className="flex items-center gap-3">
            <StockBadge stock={product.stock} size="md" />
            <span className="font-body text-xs text-ink-soft/50">Product ID #{product.id}</span>
          </div>

          {statusMessage && (
            <p className="rounded-md bg-moss-light/20 px-3 py-2 font-body text-sm font-medium text-moss-dark">{statusMessage}</p>
          )}

          {product.is_active === false ? (
            <p className="rounded-md border border-putty-dark bg-putty-light/40 px-3 py-2 font-body text-sm text-ink-soft">This product is no longer listed.</p>
          ) : !inStock ? (
            <p className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 font-body text-sm text-rose-700">Out of stock — this item can't be added to the cart right now.</p>
          ) : (
            <label className="flex items-center gap-2 font-body text-sm text-ink-soft">
              Quantity
              <input
                type="number"
                min="1"
                max={product.stock}
                value={qty}
                onChange={(e) => setQuantity(Number(e.target.value) || 1)}
                className="w-20 rounded-sm border border-putty-dark bg-ivory px-2 py-1 text-ink focus:border-clay focus:outline-none"
              />
              <span className="text-xs text-ink-soft/60">of {product.stock} available</span>
            </label>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleBuyNow}
              disabled={!inStock || checkingOut}
              className="rounded-sm bg-clay px-5 py-2.5 font-body text-sm font-semibold text-ivory shadow-sm transition-colors hover:bg-clay-dark disabled:bg-putty disabled:text-ink-soft/50"
            >
              {checkingOut ? "Opening checkout..." : "Buy Now"}
            </button>
            <button
              onClick={handleAddToCart}
              disabled={!inStock}
              className="rounded-sm border border-clay px-5 py-2.5 font-body text-sm font-medium text-clay transition-colors hover:bg-putty-light disabled:border-putty-dark disabled:text-ink-soft/40"
            >
              Add to Cart
            </button>
          </div>

          <PricingPolicyCard price={product.price} negotiable={product.negotiable} />
          <EmiOptions price={product.price} />
        </div>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-8 md:grid-cols-3">
        <div className="md:col-span-2">
          <h2 className="mb-3 font-body text-sm font-semibold uppercase tracking-wide text-ink-soft">Reviews</h2>
          <ReviewsList reviews={product.reviews} />
        </div>
      </div>

      <div className="mt-10">
        <RecommendationsRow allProducts={allProducts} currentProduct={product} />
      </div>
    </div>
  );
}
