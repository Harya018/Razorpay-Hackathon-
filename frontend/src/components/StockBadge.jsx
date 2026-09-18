// Real stock status only — every number here comes straight from
// product.stock (backend/app/schemas/product.py's real `stock` column).
// Nothing here is invented: no fabricated "max capacity", no synthetic
// percentage bar unless a real denominator exists.
const LOW_STOCK_THRESHOLD = 5;

export function stockStatus(stock) {
  if (stock == null) return null;
  if (stock <= 0) return "out";
  if (stock <= LOW_STOCK_THRESHOLD) return "low";
  return "in";
}

const LABEL = { in: "In Stock", low: "Low Stock", out: "Out of Stock" };
const DOT_CLASS = { in: "bg-moss", low: "bg-amber-500", out: "bg-rose-600" };
const TEXT_CLASS = { in: "text-moss-dark", low: "text-amber-700", out: "text-rose-700" };

// size: "sm" (product cards, dense lists) | "md" (product detail, cart lines)
export default function StockBadge({ stock, size = "sm", showCount = true }) {
  const status = stockStatus(stock);
  if (status === null) return null;

  const textSize = size === "md" ? "text-xs" : "text-[11px]";
  return (
    <span className={`inline-flex items-center gap-1.5 font-body ${textSize} font-medium ${TEXT_CLASS[status]}`}>
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_CLASS[status]}`} aria-hidden="true" />
      {showCount && status !== "out" ? `${stock} in stock — ` : ""}
      {LABEL[status]}
    </span>
  );
}
