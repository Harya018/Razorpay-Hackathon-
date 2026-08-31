"""Priya's actual negotiation limits.

This file is deliberately just config, not logic — it should read like
something Priya could review and edit herself, not code someone has to
trace through. Nothing outside this file decides what a discount is
allowed to be; the evaluation logic in routes/evaluate.py only ever reads
from here.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProductRule:
    max_discount_pct: float  # 0-100 — largest % off list price ever allowed for this SKU
    floor_price: Optional[int] = None  # paise, per unit — an absolute cost floor, if one applies.
    # When set, this is an INDEPENDENT constraint from max_discount_pct (e.g.
    # "never below what we paid for it"), not a replacement for it — the
    # gate enforces whichever of the two constraints is stricter.


# Per-product overrides. Any product_id not listed here falls back to
# DEFAULT_RULE. Add a line here for any SKU that needs its own limit.
PRODUCT_RULES: dict[int, ProductRule] = {
    1: ProductRule(max_discount_pct=10.0),  # Hand-Painted Ceramic Table Vase — thinner margin, tighter cap
}

DEFAULT_RULE = ProductRule(max_discount_pct=15.0)

# The REAL authority on how many offer attempts a negotiation gets. Phase
# 2's MAX_OFFER_ATTEMPTS constant in the backend is only a conversation-
# length safety bound now (it stops the graph looping forever) — this is
# what's actually enforced against the merchant's wishes.
MAX_ATTEMPTS = 3


def get_rule(product_id: int) -> ProductRule:
    return PRODUCT_RULES.get(product_id, DEFAULT_RULE)


def min_allowed_unit_price(product_id: int, original_unit_price: int) -> int:
    """The lowest per-unit price this product may ever be sold for in a
    negotiation. Combines both constraints — the percentage cap off list
    price, and (if set) an absolute cost floor — whichever is HIGHER wins,
    since neither constraint alone is allowed to be violated.
    """
    rule = get_rule(product_id)
    pct_floor = round(original_unit_price * (1 - rule.max_discount_pct / 100))
    if rule.floor_price is not None:
        return max(pct_floor, rule.floor_price)
    return pct_floor
