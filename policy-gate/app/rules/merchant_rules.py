"""Priya's actual negotiation limits.

These constants below are the INITIAL config — what a fresh install seeds
the database with (see seed_defaults_if_empty). Once seeded, the database
(GateConfig / ProductRuleOverride, app/models/gate_config.py) is the live
source of truth: an admin can edit these values from the Merchant
Dashboard's "Policy Gate Rules" panel without touching code or
redeploying. Nothing outside this file (and its DB-backed counterparts)
decides what a discount is allowed to be; evaluate.py only ever reads the
resolved numbers this module hands back — its comparison logic is
completely unchanged by any of this.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.gate_config import GateConfig, ProductRuleOverride


@dataclass(frozen=True)
class ProductRule:
    max_discount_pct: float  # 0-100 — largest % off list price ever allowed for this SKU
    floor_price: Optional[int] = None  # paise, per unit — an absolute cost floor, if one applies.
    # When set, this is an INDEPENDENT constraint from max_discount_pct (e.g.
    # "never below what we paid for it"), not a replacement for it — the
    # gate enforces whichever of the two constraints is stricter.


# Initial per-product overrides, used only to seed the database on first
# startup (see seed_defaults_if_empty) — after that, edits go through
# ProductRuleOverride rows, not this dict.
PRODUCT_RULES: dict[int, ProductRule] = {
    1: ProductRule(max_discount_pct=10.0),  # Hand-Painted Ceramic Table Vase — thinner margin, tighter cap
}

DEFAULT_RULE = ProductRule(max_discount_pct=15.0)

# Initial value only — see GateConfig.max_attempts for the live, editable one.
MAX_ATTEMPTS = 3


def seed_defaults_if_empty(db: Session) -> None:
    """Called once at startup (see main.py). Never overwrites an existing
    row — this only ever fills in the DB the first time it's empty, so an
    admin's prior edits always survive a restart.
    """
    if db.get(GateConfig, 1) is None:
        db.add(GateConfig(id=1, default_max_discount_pct=DEFAULT_RULE.max_discount_pct, max_attempts=MAX_ATTEMPTS))
    for product_id, rule in PRODUCT_RULES.items():
        if db.query(ProductRuleOverride).filter(ProductRuleOverride.product_id == product_id).first() is None:
            db.add(ProductRuleOverride(product_id=product_id, max_discount_pct=rule.max_discount_pct, floor_price=rule.floor_price))
    db.commit()


def get_config(db: Session) -> GateConfig:
    config = db.get(GateConfig, 1)
    if config is None:
        # Defensive fallback only — seed_defaults_if_empty should already
        # have created this row at startup. Never let a missing config
        # row silently mean "no limit."
        config = GateConfig(id=1, default_max_discount_pct=DEFAULT_RULE.max_discount_pct, max_attempts=MAX_ATTEMPTS)
        db.add(config)
        db.commit()
    return config


def get_max_attempts(db: Session) -> int:
    return get_config(db).max_attempts


def get_rule(db: Session, product_id: int) -> ProductRule:
    override = db.query(ProductRuleOverride).filter(ProductRuleOverride.product_id == product_id).first()
    if override is not None:
        return ProductRule(max_discount_pct=override.max_discount_pct, floor_price=override.floor_price)
    return ProductRule(max_discount_pct=get_config(db).default_max_discount_pct)


def min_allowed_unit_price(db: Session, product_id: int, original_unit_price: int) -> int:
    """The lowest per-unit price this product may ever be sold for in a
    negotiation. Combines both constraints — the percentage cap off list
    price, and (if set) an absolute cost floor — whichever is HIGHER wins,
    since neither constraint alone is allowed to be violated.
    """
    rule = get_rule(db, product_id)
    pct_floor = round(original_unit_price * (1 - rule.max_discount_pct / 100))
    if rule.floor_price is not None:
        return max(pct_floor, rule.floor_price)
    return pct_floor
