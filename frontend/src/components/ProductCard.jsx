import { Link } from "react-router-dom";

export function StarRating({ rating, reviewCount, size = "text-sm" }) {
  if (rating == null) return null;
  const rounded = Math.round(rating * 2) / 2; // nearest half-star
  return (
    <div className={`flex items-center gap-1 ${size}`}>
      <span className="text-clay" aria-hidden="true">
        {"★".repeat(Math.floor(rounded))}
        {rounded % 1 !== 0 ? "☆" : ""}
        {"☆".repeat(5 - Math.ceil(rounded))}
      </span>
      <span className="font-body text-ink-soft">
        {rating.toFixed(1)}
        {reviewCount != null && <span className="text-ink-soft/60"> ({reviewCount})</span>}
      </span>
    </div>
  );
}

export default function ProductCard({ product }) {
  const image = product.image_urls?.[0];
  const inStock = product.stock > 0;

  return (
    <Link
      to={`/shop/product/${product.id}`}
      className="group flex flex-col overflow-hidden rounded-[3px_14px_3px_14px] border border-putty-dark bg-ivory shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="aspect-square w-full overflow-hidden bg-putty-light">
        {image ? (
          <img
            src={image}
            alt={product.name}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center font-body text-sm text-ink-soft/50">No image</div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <div className="flex items-start justify-between gap-2">
          <p className="line-clamp-2 min-w-0 flex-1 font-display text-sm font-medium text-ink">{product.name}</p>
          {product.negotiable && (
            <span className="shrink-0 rounded-full bg-moss-light/25 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-moss-dark">
              Negotiable
            </span>
          )}
        </div>
        <StarRating rating={product.rating} reviewCount={product.review_count} />
        <div className="mt-auto flex items-baseline justify-between pt-1">
          <p className="font-body text-lg font-bold text-ink">₹{(product.price / 100).toFixed(2)}</p>
          {!inStock && <span className="font-body text-xs font-medium text-rose-700">Out of stock</span>}
        </div>
      </div>
    </Link>
  );
}
