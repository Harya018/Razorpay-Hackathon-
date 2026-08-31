import { StarRating } from "./ProductCard.jsx";

// Renders the product's static, seed-time-written reviews (see
// backend/scripts/seed_catalog.py) — never generated at request time.
export default function ReviewsList({ reviews }) {
  if (!reviews || reviews.length === 0) {
    return <p className="font-body text-sm text-ink-soft/60">No reviews yet.</p>;
  }

  return (
    <ul className="space-y-4">
      {reviews.map((review, i) => (
        <li key={i} className="rounded-md border border-putty-dark bg-ivory p-4">
          <div className="flex items-center justify-between gap-2">
            <p className="font-display text-sm font-semibold text-ink">{review.author}</p>
            <StarRating rating={review.rating} size="text-xs" />
          </div>
          <p className="mt-1.5 font-body text-sm text-ink-soft">{review.text}</p>
        </li>
      ))}
    </ul>
  );
}
