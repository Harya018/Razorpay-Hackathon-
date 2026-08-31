import ProductCard from "./ProductCard.jsx";

// "Customers also viewed" — deliberately simple, per Phase 9's scope:
// other products in the same category, excluding the current one. No
// real recommendation engine, no LLM involved.
export default function RecommendationsRow({ allProducts, currentProduct, limit = 4 }) {
  if (!currentProduct?.category) return null;

  const recommendations = allProducts
    .filter((p) => p.id !== currentProduct.id && p.category === currentProduct.category)
    .slice(0, limit);

  if (recommendations.length === 0) return null;

  return (
    <div>
      <h2 className="mb-3 font-body text-sm font-semibold uppercase tracking-wide text-ink-soft">Customers also viewed</h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
        {recommendations.map((p) => (
          <ProductCard key={p.id} product={p} />
        ))}
      </div>
    </div>
  );
}
