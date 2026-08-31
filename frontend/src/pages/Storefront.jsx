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

  if (loading) return <p className="font-body text-sm text-ink-soft">Loading products...</p>;
  if (error) return <p className="font-body text-sm text-rose-700">{error}</p>;

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
