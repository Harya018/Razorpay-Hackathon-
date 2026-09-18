import { useEffect, useState } from "react";

import ProductCard from "../components/ProductCard.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

const CATEGORY_LABELS = {
  all: "All",
  decor: "Decor",
  lighting: "Lighting",
  textiles: "Textiles",
  planters: "Planters",
  tableware: "Tableware",
};

export default function Storefront() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [category, setCategory] = useState("all");

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

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="animate-pulse overflow-hidden rounded-[3px_14px_3px_14px] border border-putty-dark bg-ivory">
            <div className="aspect-square w-full bg-putty-light" />
            <div className="space-y-2 p-3">
              <div className="h-3.5 w-3/4 rounded bg-putty-light" />
              <div className="h-3.5 w-1/2 rounded bg-putty-light" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (error) return <p className="font-body text-sm text-rose-700">Couldn't load the catalog — {error}</p>;
  if (products.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-putty-dark bg-ivory p-6 text-center font-body text-sm text-ink-soft">
        No products in the catalog yet.
      </p>
    );
  }

  const categories = ["all", ...new Set(products.map((p) => p.category).filter(Boolean))];
  const visible = category === "all" ? products : products.filter((p) => p.category === category);

  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-2">
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`rounded-full px-3 py-1.5 font-body text-sm font-medium transition-colors ${
              category === c
                ? "bg-clay text-ivory"
                : "border border-putty-dark bg-ivory text-ink-soft hover:bg-putty-light"
            }`}
          >
            {CATEGORY_LABELS[c] ?? c}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {visible.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </div>
  );
}
